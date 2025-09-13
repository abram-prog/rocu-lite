
# Demo Scenarios & Checklists

## Scenario A — Happy Path (no loss)

1. Start backend:
   ```bash
   cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
2. Start simulator:
   ```bash
   cd simulator && source .venv/bin/activate && BACKEND_URL="ws://127.0.0.1:8000/ws/sim" python ugv_sim.py
   ```
3. Open UI http://127.0.0.1:8000/ and observe:
   - Telemetry JSON updates ~10Hz
   - Safety: `safe_mode=false`
4. Send a drive command (vx=0.5, wz=0.2). Check:
   - REST returns `accepted=true`
   - RTT < 50 ms (typical localhost)
   - Simulator logs command accepted

## Scenario B — Urban Loss (20% loss, 40ms delay)

1. Apply profile:
   ```bash
   sudo bash net-profiles/apply_profile.sh apply lo net-profiles/profiles/urban-lossy-20.conf
   ```
2. Observe in UI:
   - RTT spikes (100–300ms)
   - Occasional command acks delayed; if heartbeats >0.8s apart → **safe_mode=true**
3. Clear profile:
   ```bash
   sudo bash net-profiles/apply_profile.sh clear lo
   ```
4. System stabilizes; `safe_mode=false` resumes after next heartbeats.

## Scenario C — Command Starvation (safety gate)

1. Stop sending commands for >1s (don’t press Drive).
2. Backend switches to `safe_mode=true`.
3. Send any command; safe_mode exits within one cycle.

---

## Metrics to Capture (for your report)

- Command p95 RTT (no-loss vs 20% loss)
- Telemetry drop rate (UI updates per second base vs degraded)
- Safety transitions per minute under 20% loss
