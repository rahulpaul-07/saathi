import pytest

from saathi.evaluation.power import PowerError, PowerGuard, PowerState, wait_for_ac


def _reader(*states: PowerState):  # type: ignore[no-untyped-def]
    queue = list(states)
    return lambda: queue.pop(0) if len(queue) > 1 else queue[0]


@pytest.mark.parametrize("state", [PowerState.BATTERY, PowerState.UNKNOWN])
def test_guard_refuses_to_start_off_ac(state: PowerState) -> None:
    with pytest.raises(PowerError, match="plug in"):
        PowerGuard(_reader(state))


def test_allow_battery_runs_but_is_tagged_and_unknown_is_still_refused() -> None:
    assert PowerGuard(_reader(PowerState.BATTERY), allow_battery=True).state == PowerState.BATTERY
    with pytest.raises(PowerError):
        PowerGuard(_reader(PowerState.UNKNOWN), allow_battery=True)


def test_guard_fails_when_power_changes_mid_run() -> None:
    guard = PowerGuard(_reader(PowerState.AC, PowerState.AC, PowerState.BATTERY))
    guard.check()
    with pytest.raises(PowerError, match="changed from ac to battery"):
        guard.check()


def test_wait_for_ac_returns_when_plugged_in() -> None:
    slept: list[float] = []
    reader = _reader(PowerState.BATTERY, PowerState.BATTERY, PowerState.AC)
    assert wait_for_ac(reader, timeout_s=100, poll_s=5, sleep=slept.append, clock=lambda: 0)
    assert slept == [5, 5]


def test_wait_for_ac_gives_up_at_the_timeout() -> None:
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    assert not wait_for_ac(
        _reader(PowerState.BATTERY), timeout_s=20, poll_s=10, sleep=sleep, clock=lambda: now[0]
    )
