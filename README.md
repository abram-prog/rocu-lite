
# ROCU‑Lite Edge Stack (Sprint 1)

**Goal (Sprint 1):** establish a minimal yet *realistic* operator–edge skeleton:
- Backend on Linux (FastAPI + WebSocket) with **heartbeat & safety gate**
- Simulator that mimics a UGV: sends telemetry, receives drive commands
- Minimal **operator UI** (web) to view live telemetry and send commands
- **Network degradation** emulation via `tc/netem` profiles
- Docker Compose + Makefile for fast spin‑up

This lays the groundwork for Sprint 2 (video RTP→WebRTC, bitrate adaptation) and Sprint 3 (mission/waypoints + map).

---

## 0) Requirements

- Linux (preferred) or WSL2. Python 3.11+.
- For network emulation: `tc` (iproute2) + root privileges.
- Docker + Docker Compose (optional but recommended).

## 1) Quick Start (host, no Docker)

```bash
# 1) Create and activate venv for backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) Run backend (FastAPI + WebSocket + static UI)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

In a new terminal, run the simulator:
```bash
cd simulator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
BACKEND_URL="ws://127.0.0.1:8000/ws/sim" python ugv_sim.py
```

Open the operator UI: http://127.0.0.1:8000/

- You should see live telemetry updating ~10 Hz
- Use **Drive** controls to send commands; observe command timestamps and safety state

## 2) Docker Compose (optional)

```bash
make up      # builds and starts backend + simulator
make logs    # follow logs
make down    # stop & remove
```

Then open http://127.0.0.1:8000/

## 3) Network Degradation (tc/netem)

> Requires Linux + root. These scripts shape the **loopback** `lo` device to simulate MANET-like loss/jitter even when all services run locally.

```bash
# Show available profiles
ls net-profiles/profiles

# Apply a profile (e.g., urban-lossy-20)
sudo bash net-profiles/apply_profile.sh apply lo net-profiles/profiles/urban-lossy-20.conf

# Clear shaping
sudo bash net-profiles/apply_profile.sh clear lo
```

**Profiles included:**
- `good.conf` — baseline fair link (~1ms, no loss)
- `urban-lossy-20.conf` — 20% loss, 40ms avg delay, 20ms jitter
- `tunnel-lossy-40.conf` — 40% loss, 120ms avg delay, 50ms jitter

The UI will show increased command RTT and may trigger **safe mode** if heartbeats lapse.

## 4) Sprint 1 Scope & What to Look For

- **Heartbeat & Safety Gate:** backend expects a command/heartbeat at least every 0.8s; otherwise enters safe mode (robot must stop).
- **Telemetry Broadcast:** simulator pushes telemetry over WebSocket; backend fans out to UI clients.
- **Command Path:** UI → REST → backend → WebSocket → simulator (with ack + RTT metric).

## 5) Sprint 2/3 Preview (coming next)

- **S2 Video Gateway:** RTP/RTSP → WebRTC relay w/ bitrate adaptation (x264/openh264); TURN for NAT traversal; degradation-aware downsampling.
- **S3 Mission/Waypoints + Map:** KML/GeoJSON import, mission logger (JSONL/CSV), QoS indicators.

---

## Repo Map

```
rocu-lite/
  backend/
    app/
      main.py         # FastAPI app, WS endpoints, routes
      schemas.py      # Pydantic models
      state.py        # In-memory state + metrics
    static/
      index.html      # Minimal operator UI (telemetry + drive)
    requirements.txt
    Dockerfile
  simulator/
    ugv_sim.py        # UGV simulator: telemetry + drive commands
    requirements.txt
  net-profiles/
    apply_profile.sh  # tc/netem wrapper
    profiles/
      good.conf
      urban-lossy-20.conf
      tunnel-lossy-40.conf
  docs/
    demo_scenarios.md # Step-by-step demo scripts & metrics
  .github/workflows/ci.yml
  docker-compose.yml
  Makefile
```

## Demo Scenarios (short)

See `docs/demo_scenarios.md` for detailed steps, including suggested screenshots and CSV exports.

---

## API Sketch

- `POST /api/v1/cmd/drive` → `{vx, vy, wz}`; returns `{accepted, ts, rtt_ms}`
- `GET  /api/v1/metrics`    → current safety/heartbeat/clients counters
- `WS   /ws/sim`            → bidirectional sim channel (`telemetry` / `command` messages)
- `WS   /ws/telemetry`      → broadcast telemetry to UI clients

---

## Notes

- This is **educational** skeleton code with production-minded patterns (timeouts, acks, RTT). For real robots, harden authN/Z, persistence, and RT constraints.
- For Windows/macOS without `tc`: skip netem; you still can test heartbeat/RTT and UI/command flow.
