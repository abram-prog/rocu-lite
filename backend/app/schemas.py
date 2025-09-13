
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from typing import List

class TelemetryFrame(BaseModel):
    ts: float = Field(..., description="Unix timestamp (seconds)")
    seq: int
    imu_ax: float
    imu_ay: float
    imu_az: float
    yaw: float
    pitch: float
    roll: float
    lat: float
    lon: float
    vx: float
    vy: float
    wz: float

class DriveCommand(BaseModel):
    ts: float
    vx: float  # forward m/s 
    vy: float  # lateral m/s
    wz: float  # yaw rate rad/s

class Waypoint(BaseModel):
    lat: float
    lon: float
    hold_s: float = 0.0

class Mission(BaseModel):
    waypoints: List[Waypoint]

class CommandAck(BaseModel):
    accepted: bool
    ts: float
    rtt_ms: float

class Metrics(BaseModel):
    safe_mode: bool
    last_cmd_ts: Optional[float] = None
    last_telemetry_ts: Optional[float] = None
    telemetry_clients: int
    sim_connected: bool
    uptime_s: float
