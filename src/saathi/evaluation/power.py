"""Power state of the laptop. Latency on battery is 10-20x slower, so it must never be mixed in."""

import ctypes
import sys
import time
from collections.abc import Callable
from enum import StrEnum


class PowerState(StrEnum):
    AC = "ac"
    BATTERY = "battery"
    UNKNOWN = "unknown"


class PowerError(RuntimeError):
    """The machine is not on AC power, or its power state changed during a run."""


class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),  # 0 offline, 1 online, 255 unknown
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def read_power_state() -> PowerState:
    """Ask Windows (GetSystemPowerStatus). Any other platform reports UNKNOWN."""
    if sys.platform != "win32":
        return PowerState.UNKNOWN
    status = _SystemPowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return PowerState.UNKNOWN
    return {1: PowerState.AC, 0: PowerState.BATTERY}.get(status.ACLineStatus, PowerState.UNKNOWN)


class PowerGuard:
    """Pins the power state at the start of a run and fails if it changes.

    With `allow_battery` a battery run is permitted but is still tagged by `state`, so the results
    say what they were measured on. UNKNOWN is never accepted: an unreadable state cannot be
    certified as AC.
    """

    def __init__(
        self,
        reader: Callable[[], PowerState] = read_power_state,
        *,
        allow_battery: bool = False,
    ) -> None:
        self._reader = reader
        self.state = reader()
        accepted = {PowerState.AC, PowerState.BATTERY} if allow_battery else {PowerState.AC}
        if self.state not in accepted:
            raise PowerError(
                f"power state is {self.state.value}; plug in AC power "
                "(or pass --allow-battery to run and tag the results as battery)"
            )

    def check(self) -> None:
        """Call before each measured unit of work."""
        current = self._reader()
        if current != self.state:
            raise PowerError(f"power state changed from {self.state.value} to {current.value}")


def wait_for_ac(
    reader: Callable[[], PowerState] = read_power_state,
    *,
    timeout_s: float,
    poll_s: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Block until the machine is on AC power. False if `timeout_s` passes first."""
    deadline = clock() + timeout_s
    while reader() != PowerState.AC:
        if clock() >= deadline:
            return False
        sleep(poll_s)
    return True
