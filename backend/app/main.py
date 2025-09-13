import math
import time
import json
import asyncio
from typing import List, Dict, Any

_qos_log: list[Dict] = []

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .schemas import TelemetryFrame, DriveCommand, CommandAck, Metrics, Mission, Waypoint
from .state import STATE, MISSION

app = FastAPI(title="ROCU-Lite Backend", version="0.1.0")

@app.on_event("startup")
async def _startup():
    asyncio.create_task(mission_driver())

@app.get("/health")
def health():
    return {"status": "ok", "uptime_s": STATE.uptime()}

@app.get("/api/v1/metrics", response_model=Metrics)
def metrics():
    return Metrics(
        safe_mode=STATE.safe_mode,
        last_cmd_ts=STATE.last_cmd_ts,
        last_telemetry_ts=STATE.last_telemetry_ts,
        telemetry_clients=len(STATE.telemetry_clients),
        sim_connected=STATE.sim_websocket is not None,
        uptime_s=STATE.uptime(),
    )

@app.post("/api/v1/cmd/drive", response_model=CommandAck)
async def cmd_drive(cmd: DriveCommand, request: Request):
    # Update heartbeat timestamp
    STATE.last_cmd_ts = time.time()
    STATE.last_cmd_mono = time.monotonic()

    # Forward to simulator if connected; measure RTT via explicit ack
    start = time.time()
    accepted = False
    if STATE.sim_websocket is not None:
        try:
            payload = {
                "type": "command",
                "command": "drive",
                "data": cmd.model_dump(),
            }
            await STATE.sim_websocket.send_text(json.dumps(payload))

            # Wait briefly for ack (non-blocking timeout)
            # In a more robust system, use correlation IDs
            await asyncio.sleep(0.01)
            accepted = True
        except Exception:
            accepted = False

    rtt_ms = (time.time() - start) * 1000.0
    return CommandAck(accepted=accepted, ts=time.time(), rtt_ms=rtt_ms)

@app.websocket("/ws/telemetry")
async def ws_telemetry(websocket: WebSocket):
    await websocket.accept()
    STATE.telemetry_clients.add(websocket)
    try:
        while True:
            # This is a pure broadcast socket; we don't expect messages from UI
            msg = await websocket.receive_text()
            # Ignore any incoming (simple keepalive if user sends pings)
    except WebSocketDisconnect:
        STATE.telemetry_clients.discard(websocket)
    except Exception:
        STATE.telemetry_clients.discard(websocket)

@app.websocket("/ws/sim")
async def ws_sim(websocket: WebSocket):
    await websocket.accept()
    STATE.sim_websocket = websocket
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                obj = json.loads(raw)
            except Exception:
                continue

            if obj.get("type") == "telemetry":
                # Validate + broadcast
                try:
                    frame = TelemetryFrame(**obj["data"])
                    frame.yaw = math.atan2(math.sin(frame.yaw), math.cos(frame.yaw))
                    STATE.last_telemetry_ts = time.time()
                    STATE.last_telemetry_mono = time.monotonic()

                    STATE.last_frame = frame

                    d = frame.model_dump()
                    d["yaw_deg"] = round(math.degrees(d["yaw"]), 1)
                    
                    # Broadcast to UI clients (best-effort)
                    await _broadcast_to_clients(json.dumps({"type": "telemetry", "data": d}))

                except Exception:
                    # Ignore malformed frames
                    pass
            else:
                # future: handle sim acks, etc.
                pass
    except WebSocketDisconnect:
        STATE.sim_websocket = None
    except Exception:
        STATE.sim_websocket = None

async def _broadcast_to_clients(text: str):
    if not STATE.telemetry_clients:
        return
    dead = []
    for ws in list(STATE.telemetry_clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        STATE.telemetry_clients.discard(ws)

async def mission_driver():
    while True:
        await asyncio.sleep(0.2)
        if not (MISSION.active and not MISSION.paused and STATE.sim_websocket and MISSION.waypoints):
            continue

        cur = getattr(STATE, "last_frame", None)
        if not cur:
            continue

        # если включён RTL и есть home — едем домой, иначе к текущему WP
        if getattr(MISSION, "rtl", False) and getattr(MISSION, "home", None):
            target = MISSION.home
        else:
            idx = min(MISSION.current_idx, len(MISSION.waypoints) - 1)
            target = MISSION.waypoints[idx]

        # Приблизительная метрика "градусы → метры" на малых расстояниях
        dlat = (target["lat"] - cur.lat) * 111_111.0
        dlon = (target["lon"] - cur.lon) * 111_111.0 * math.cos(math.radians(cur.lat))
        dist = math.hypot(dlat, dlon)

        # Достигли точки → переключаемся
        if dist < 2.0:
            if getattr(MISSION, "rtl", False):
                # приехали домой — выключаем автопилот и RTL, шлём стоп
                MISSION.active = False
                MISSION.rtl = False
                try:
                    if STATE.sim_websocket:
                        await STATE.sim_websocket.send_text(json.dumps({
                            "type": "command", "command": "drive",
                            "data": {"ts": time.time(), "vx": 0.0, "vy": 0.0, "wz": 0.0}
                        }))
                except Exception:
                    pass
            else:
                # обычная миссия — следующая точка, а на финале стоп
                MISSION.current_idx = min(len(MISSION.waypoints) - 1, MISSION.current_idx + 1)
                if MISSION.current_idx == len(MISSION.waypoints) - 1:
                    MISSION.active = False
                    try:
                        if STATE.sim_websocket:
                            await STATE.sim_websocket.send_text(json.dumps({
                                "type": "command", "command": "drive",
                                "data": {"ts": time.time(), "vx": 0.0, "vy": 0.0, "wz": 0.0}
                            }))
                    except Exception:
                        pass
            continue

        # P-контроллер с насыщением
        vx = max(-1.0, min(1.0, dlat * 0.05))
        vy = max(-1.0, min(1.0, dlon * 0.05))

        cmd = {
            "type": "command",
            "command": "drive",
            "data": {"ts": time.time(), "vx": vx, "vy": vy, "wz": 0.0},
        }

        try:
            await STATE.sim_websocket.send_text(json.dumps(cmd))
        except Exception:
            pass

        # Лог JSONL → потом скачиваем /api/v1/mission/log.csv
        try:
            with open(MISSION.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": time.time(),
                    "lat": cur.lat, "lon": cur.lon,
                    "vx": cur.vx, "vy": cur.vy, "wz": cur.wz,
                    "idx": idx
                }) + "\n")
        except Exception:
            pass

from fastapi import Body
from .video import create_pc_and_answer, set_max_kbps, document_max_kbps

@app.api_route("/api/v1/webrtc/offer", methods=["GET", "POST"])
@app.api_route("/api/v1/webrtc/offer/", methods=["GET", "POST"])
async def webrtc_offer(payload: dict | None = Body(None)):
    # payload может быть None при GET – пусть будет безопасный разбор
    sdp = (payload or {}).get("sdp", "")
    typ = (payload or {}).get("type", "offer")
    max_kbps = int((payload or {}).get("max_kbps", 1500))
    set_max_kbps(max_kbps)
    answer_sdp, answer_type = await create_pc_and_answer(sdp, typ, max_kbps)
    return {"sdp": answer_sdp, "type": answer_type}

@app.post("/api/v1/webrtc/qos")
async def webrtc_qos(payload: Dict = Body(...)):
    """
    Принимает метрики из фронта:
    {
      "bitrate_kbps": 1234,
      "jitter": 0.012,        # сек
      "rtt_ms": 85
    }
    Возвращает рекомендацию по новому max_kbps (или null).
    """
    import os, json, time

    LOG_PATH = os.environ.get("QOS_LOG", "/tmp/rocu_qos.jsonl")

    # не мутируем исходный payload, добавим timestamp в копию
    record = dict(payload)
    record.setdefault("ts", time.time())

    # пишем одну JSON-строку (JSONL)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    recommend = None
    bitrate = payload.get("bitrate_kbps") or 0
    jitter  = payload.get("jitter") or 0.0
    rtt_ms  = payload.get("rtt_ms") or 0

    # простая политика: если плохо — снизить на 25% от текущего, но не ниже 300
    if (bitrate and bitrate < 600) or (jitter > 0.04) or (rtt_ms > 250):
        try:
            cur = int(document_max_kbps())
        except Exception:
            cur = 1500
        recommend = max(300, int(cur * 0.75))

    return {"recommend_max_kbps": recommend}

@app.post("/api/v1/mission")
async def set_mission(m: Mission):
    MISSION.waypoints = [w.model_dump() for w in m.waypoints]
    MISSION.current_idx = 0
    return {"ok": True, "count": len(MISSION.waypoints)}

@app.post("/api/v1/mission/control")
async def mission_ctrl(payload: dict = Body(...)):
    act = (payload.get("action") or "").upper()

    if act == "GO":
        MISSION.active = True
        MISSION.paused = False
        # выключаем RTL-режим и один раз запоминаем "дом"
        MISSION.rtl = False
        try:
            if not getattr(MISSION, "home", None) and getattr(STATE, "last_frame", None):
                MISSION.home = {"lat": STATE.last_frame.lat, "lon": STATE.last_frame.lon}
        except Exception:
            pass

    elif act == "PAUSE":
        MISSION.paused = True
        # сразу отправим стоп, чтобы сим реально остановился
        try:
            if STATE.sim_websocket:
                await STATE.sim_websocket.send_text(json.dumps({
                    "type": "command", "command": "drive",
                    "data": {"ts": time.time(), "vx": 0.0, "vy": 0.0, "wz": 0.0}
                }))
        except Exception:
            pass

    elif act == "RTL":
        # включаем возврат домой — цель будет выбрана в mission_driver()
        MISSION.active = True
        MISSION.paused = False
        MISSION.rtl = True

    return {"ok": True, "state": {
        "active": MISSION.active, "paused": MISSION.paused,
        "idx": MISSION.current_idx, "rtl": getattr(MISSION, "rtl", False)
    }}

@app.get("/api/v1/mission/log.csv")
def mission_csv():
    # на лету из JSONL соберём CSV
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ts","lat","lon","vx","vy","wz","idx"])
    try:
        with open(MISSION.log_path, "r", encoding="utf-8") as f:
            for line in f:
                j = json.loads(line)
                w.writerow([j.get("ts"), j.get("lat"), j.get("lon"), j.get("vx"), j.get("vy"), j.get("wz"), j.get("idx")])
    except FileNotFoundError:
        pass
    return HTMLResponse(content=buf.getvalue(), media_type="text/csv")

# Serve minimal operator UI
app.mount("/", StaticFiles(directory="static", html=True), name="static")
