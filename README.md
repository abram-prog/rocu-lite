# ROCU-Lite — Edge Control + Video + Mission (S1–S3)

**Overview.** Minimal operator ↔ UGV stack built for reliability under poor networks:

- **S1 – Control & Telemetry:** FastAPI backend, WebSocket telem fan-out, heartbeat/safety gate, tc/netem profiles.
- **S2 – Video (WebRTC):** server-side WebRTC answer (aiortc), synthetic/USB/RTSP source, max bitrate cap.
- **S3 – Mission (basics):** map UI, waypoints, simple mission driver (move-to-WP), CSV logging.

> No Docker Compose required. Everything runs with local Python venvs.

---

## Quickstart (local, no Docker)

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Simulator (new terminal)

```bash

cd simulator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
BACKEND_URL="ws://127.0.0.1:8000/ws/sim" python ugv_sim.py
```

Then open: [http://127.0.0.1:8000/](http://127.0.0.1:8000/) — you should see live telemetry, drive commands, and the Video (WebRTC) panel.

---

## S2 – Video (WebRTC)

Default source is **synthetic** (moving bars).  
To use a real source:

```bash

# USB webcam (index 0):
export VIDEO_SRC=0
```
### or RTSP:
```bash
export VIDEO_SRC="rtsp://user:pass@camera-ip/path"
```

In UI press **Start**. You can lower *Max bitrate (kbps)* for harsh networks.


## Network degradation (tc/netem)

Linux/WSL2 + root required. We shape the loopback `lo` to mimic MANET loss/jitter.


```bash

# apply a profile
sudo bash net-profiles/apply_profile.sh apply lo net-profiles/profiles/urban-lossy-20.conf

# clear shaping
sudo bash net-profiles/apply_profile.sh clear lo
```

Profiles available: `good.conf`, `urban-lossy-20.conf`, `tunnel-lossy-40.conf`.

---

## S3 – Mission (basics)

**Add waypoints on the map → Send Mission → GO/PAUSE/RESUME/RTL/STOP.**
The driver steers the simulated UGV towards the current WP (simple proportional control).

Logs: download from `/api/v1/mission/log.csv` (timestamp, state, idx, lat/lon, velocities).


**API sketch:**

- `POST /api/v1/cmd/drive` → `{vx, vy, wz}` → `{accepted, ts, rtt_ms}`
- `GET /api/v1/metrics` → safety/heartbeat/client counters
- `WS /ws/sim` → simulator channel (telemetry / commands)
- `WS /ws/telemetry` → broadcast telemetry to UI
- `POST /api/v1/webrtc/offer` → SDP offer → SDP answer (WebRTC)
- `POST /api/v1/mission`
- `POST /api/v1/mission/control`
- `GET /api/v1/mission/log.csv`

---

## Repo map

```
rocu-lite/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── schemas.py
│   │   ├── state.py
│   │   └── video.py
│   ├── requirements.txt
│   └── static/
│       └── index.html
├── simulator/
│   ├── requirements.txt
│   └── ugv_sim.py
├── net-profiles/
│   ├── apply_profile.sh
│   └── profiles/
│       ├── good.conf
│       ├── tunnel-lossy-40.conf
│       └── urban-lossy-20.conf
├── docs/
│   └── demo_scenarios.md
├── LICENSE
└── README.md
```

Optional files (if present): `backend/Dockerfile` (build convenience).  
We intentionally do **not** use Docker Compose for local runs.

---

## Roadmap (next)

- **S3.1 Mission+:** hold_s, rich mission states, WS mission status.
- **S3.2 UX+:** route/ETA, event timeline, geofences.
- **S2.x QoS+:** TURN option and fine-grained bitrate adaptation without renegotiation.

---

## Troubleshooting

- **WebRTC no video:** check browser console, verify `VIDEO_SRC`, and firewall (UDP/ICE).
- **Netem requires root:** run apply/clear with `sudo`.
- **Simulator not connected:** check `BACKEND_URL` and backend logs.
