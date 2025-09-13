
import asyncio
import json
import math
import os
import random
import time
import websockets

BACKEND_URL = os.getenv("BACKEND_URL", "ws://127.0.0.1:8000/ws/sim")

async def run_sim():
    seq = 0
    yaw = 0.0
    lat, lon = 32.0853, 34.7818  # TLV-ish
    vx, vy, wz = 0.0, 0.0, 0.0
    prev_mono = time.monotonic()  # <— добавили монотонные часы
    print(f"[sim] connecting to {BACKEND_URL}")
    
    async with websockets.connect(BACKEND_URL, ping_interval=10, ping_timeout=10) as ws:
        print("[sim] connected")
        last_cmd_ts = 0.0

        async def sender():
            nonlocal prev_mono, seq, yaw, lat, lon, vx, vy, wz
            while True:

                # integrate yaw and position a bit (toy model)
                ts = time.time()

                # реальный шаг по времени
                now_mono = time.monotonic()
                dt = min(0.2, now_mono - prev_mono)   # страховка от больших скачков
                prev_mono = now_mono

                # интеграция и нормализация курса
                yaw += wz * dt
                yaw = math.atan2(math.sin(yaw), math.cos(yaw))   # [-pi, pi]

                # позиция с тем же dt
                lat += (vx * dt) / 111111.0
                lon += (vy * dt) / (111111.0 * math.cos(math.radians(lat)))
                
                frame = {
                    "ts": ts,
                    "seq": seq,
                    "imu_ax": random.uniform(-0.05, 0.05),
                    "imu_ay": random.uniform(-0.05, 0.05),
                    "imu_az": 9.81 + random.uniform(-0.05, 0.05),
                    "yaw": yaw,
                    "pitch": 0.0,
                    "roll": 0.0,
                    "lat": lat,
                    "lon": lon,
                    "vx": vx,
                    "vy": vy,
                    "wz": wz,
                }
                seq += 1
                await ws.send(json.dumps({"type": "telemetry", "data": frame}))
                await asyncio.sleep(0.1)  # ~10 Hz

        async def receiver():
            nonlocal vx, vy, wz, last_cmd_ts
            async for msg in ws:
                try:
                    obj = json.loads(msg)
                except Exception:
                    continue
                if obj.get("type") == "command" and obj.get("command") == "drive":
                    data = obj.get("data", {})
                    vx = float(data.get("vx", 0.0))
                    vy = float(data.get("vy", 0.0))
                    wz = float(data.get("wz", 0.0))
                    last_cmd_ts = time.time()
                    print(f"[sim] drive cmd: vx={vx:.2f} vy={vy:.2f} wz={wz:.2f}")
                else:
                    # ignore others for now
                    pass

        await asyncio.gather(sender(), receiver())

if __name__ == "__main__":
    try:
        asyncio.run(run_sim())
    except KeyboardInterrupt:
        pass
