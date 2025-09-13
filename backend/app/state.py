
import asyncio
import time
from typing import Set, Optional

class GlobalState:
    def __init__(self, heartbeat_timeout: float = 0.8):
        # wall-clock: только для UI/логов
        self.start_ts = time.time()
        # monotonic: для расчётов (не дергается от NTP)
        self.start_mono = time.monotonic()

        self.heartbeat_timeout = heartbeat_timeout

        # wall-clock штампы (для отображения)
        self.last_cmd_ts: Optional[float] = None
        self.last_telemetry_ts: Optional[float] = None

        # monotonic штампы (для расчёта возраста событий)
        self.last_cmd_mono: Optional[float] = None
        self.last_telemetry_mono: Optional[float] = None

        self.telemetry_clients: Set = set()
        self.sim_websocket = None  # single sim connection
        self._lock = asyncio.Lock()
        self.last_frame = None

    # Возраст последней команды/телеметрии в секундах (по monotonic)
    def cmd_age(self) -> float:
        return 1e9 if self.last_cmd_mono is None else (time.monotonic() - self.last_cmd_mono)

    def telemetry_age(self) -> float:
        return 1e9 if self.last_telemetry_mono is None else (time.monotonic() - self.last_telemetry_mono)

    @property
    def safe_mode(self) -> bool:
        # Dead-man switch: нет команд дольше порога → стоп
        return self.cmd_age() > self.heartbeat_timeout

    @safe_mode.setter
    def safe_mode(self, value: bool):
        # Сеттер оставлен для совместимости; если хочешь жёстко управлять вручную,
        # можно хранить override-флаг. По умолчанию игнорируем и не меняем расчётную логику.
        pass

    def uptime(self) -> float:
        return time.time() - self.start_ts
STATE = GlobalState()
class MissionState:
    def __init__(self):
        self.home = None      # {'lat':..., 'lon':...}
        self.rtl  = False
        self.active = False
        self.paused = False
        self.waypoints = []
        self.current_idx = 0
        self.log_path = "/tmp/rocu_mission.jsonl"

MISSION = MissionState()
