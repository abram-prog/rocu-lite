import asyncio, os, time, fractions, cv2, av
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay, MediaPlayer

CURRENT_MAX_KBPS = 1500
def set_max_kbps(v:int):
    global CURRENT_MAX_KBPS
    CURRENT_MAX_KBPS = int(v)
def document_max_kbps():
    return CURRENT_MAX_KBPS

_relay = MediaRelay()

class SyntheticVideoTrack(VideoStreamTrack):
    kind = "video"
    def __init__(self, fps: int = 20, width: int = 640, height: int = 360):
        super().__init__()
        self._fps = fps
        self._width = width
        self._height = height
        self._start = time.time()

    async def recv(self):

        # получаем согласованные PTS и time_base от базового класса
        pts, time_base = await self.next_timestamp()
        import numpy as np
        t = int((time.time() - self._start) * 1000)
        img = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        x = (t // 10) % self._width
        y = (t // 15) % self._height
        img[:, x:x+10, :] = (0,255,0)
        img[y:y+10, :, :] = (255,255,255)
        cv2.putText(img, "ROCU-Lite Synthetic", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 1,(200,200,200),2)
        frame = av.VideoFrame.from_ndarray(img, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

class OpenCVCaptureTrack(VideoStreamTrack):
    kind = "video"
    def __init__(self, src):
        super().__init__()
        self.cap = cv2.VideoCapture(src)


    async def recv(self):
        # таймкоды от базового класса (темп тоже задаётся тут)
        pts, time_base = await self.next_timestamp()
        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("Video source ended")
        frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

async def create_pc_and_answer(sdp_offer: str, type_offer: str, max_kbps: int = 1500):
    # выставим ограничение битрейта, если используешь это где-то ещё
    from .video import set_max_kbps
    set_max_kbps(int(max_kbps))

    pc = RTCPeerConnection()

    # ---------- выбор источника ----------
    src = os.getenv("VIDEO_SRC", "").strip()
    print(f"[webrtc] VIDEO_SRC={src!r}")

    track = None

    # 1) Пытаемся через ffmpeg/MediaPlayer (лучше для файлов/rtsp)
    if src:
        try:
            # Для RTSP можно options={"rtsp_transport": "tcp"}
            player = MediaPlayer(src)
            if player and player.video:
                track = player.video
                print("[webrtc] using MediaPlayer video track")
        except Exception as e:
            print(f"[webrtc] MediaPlayer failed: {e}")

    # 2) Фолбэк на OpenCV (удобно для локальной камеры/файла)
    if track is None and src:
        try:
            cam_or_file = int(src) if src.isdigit() else src
            ocv = OpenCVCaptureTrack(cam_or_file)
            # sanity-check: если это камера/файл, убедимся, что открыт
            if hasattr(ocv, "cap") and not ocv.cap.isOpened():
                raise RuntimeError(f"cv2 cannot open {src}")
            track = ocv
            print("[webrtc] using OpenCV capture track")
        except Exception as e:
            print(f"[webrtc] OpenCV failed: {e}; falling back to synthetic")

    # 3) Финальный фолбэк — синтетика (полосы и надпись)
    if track is None:
        track = SyntheticVideoTrack(fps=15, width=1280, height=720)
        print("[webrtc] using SyntheticVideoTrack")
    # -------------------------------------

    # Подключаем трек (через relay — как у тебя было)
    sender = pc.addTrack(_relay.subscribe(track))

    # Ограничение битрейта (kbps -> bps), с нижним порогом
    try:
        params = sender.getParameters()
        if not params.encodings:
            params.encodings = [{}]
        params.encodings[0]["maxBitrate"] = int(max(250_000, max_kbps * 1000))
        await sender.setParameters(params)
    except Exception as e:
        print(f"[webrtc] setParameters failed: {e}")

    # SDP: принимаем offer, создаём answer
    offer = RTCSessionDescription(sdp=sdp_offer, type=type_offer)
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return pc.localDescription.sdp, pc.localDescription.type
