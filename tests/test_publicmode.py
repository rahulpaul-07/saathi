import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import SecretStr

from saathi.config import Settings
from saathi.demobundle import BUNDLE_NAME, BUNDLE_VERSION, load_bundle
from saathi.gnani import STT_PATH, GnaniClient, GnaniError, LiveSpeechUnavailable
from saathi.publicmode import (
    GnaniBudget,
    LiveGate,
    client_ip,
    parse_trusted_proxies,
)

BASE = "https://api.test"
PROXIES = parse_trusted_proxies("10.0.0.0/8, 192.168.1.5")


def test_default_settings_leave_public_mode_off() -> None:
    settings = Settings(gnani_api_key=SecretStr("k"))
    assert settings.public_mode is False
    assert settings.kill_switch is False
    assert settings.trusted_proxies == ""


def test_forwarded_header_is_ignored_when_the_peer_is_not_a_trusted_proxy() -> None:
    # A direct client can send any X-Forwarded-For; believing it would let it dodge every limit.
    assert client_ip("203.0.113.9", "198.51.100.1", PROXIES) == "203.0.113.9"


def test_forwarded_header_is_ignored_with_no_trusted_proxies() -> None:
    assert client_ip("10.0.0.2", "198.51.100.1", ()) == "10.0.0.2"


def test_trusted_peer_gives_the_client_from_the_forwarded_header() -> None:
    assert client_ip("10.0.0.2", "198.51.100.1", PROXIES) == "198.51.100.1"


def test_spoofed_left_entries_are_skipped_in_favour_of_what_our_proxy_appended() -> None:
    # The client forged "1.1.1.1"; our proxy appended the address it actually saw.
    assert client_ip("10.0.0.2", "1.1.1.1, 198.51.100.1", PROXIES) == "198.51.100.1"


def test_chained_trusted_proxies_are_walked_past() -> None:
    assert client_ip("10.0.0.2", "198.51.100.1, 10.0.0.7, 192.168.1.5", PROXIES) == "198.51.100.1"


def test_unparseable_forwarded_entry_falls_back_to_the_peer() -> None:
    assert client_ip("10.0.0.2", "not-an-ip", PROXIES) == "10.0.0.2"
    assert client_ip("10.0.0.2", "198.51.100.1, garbage", PROXIES) == "10.0.0.2"


def test_missing_forwarded_header_and_missing_peer() -> None:
    assert client_ip("10.0.0.2", None, PROXIES) == "10.0.0.2"
    assert client_ip(None, "198.51.100.1", PROXIES) == "unknown"


def test_ipv6_clients_are_supported() -> None:
    assert client_ip("10.0.0.2", "2001:db8::1", PROXIES) == "2001:db8::1"


def test_bad_trusted_proxy_entry_fails_loudly() -> None:
    with pytest.raises(ValueError):
        parse_trusted_proxies("10.0.0.0/8, not-a-network")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 2, 23, 59, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def test_budget_counts_up_then_refuses(tmp_path: Path) -> None:
    budget = GnaniBudget(tmp_path / "b.json", 2, Clock())
    budget.spend()
    budget.spend()
    assert budget.remaining() == 0
    with pytest.raises(LiveSpeechUnavailable) as caught:
        budget.spend()
    assert caught.value.reason == "budget"


def test_budget_resets_at_the_utc_day_boundary_and_survives_a_restart(tmp_path: Path) -> None:
    clock = Clock()
    path = tmp_path / "b.json"
    GnaniBudget(path, 1, clock).spend()
    # A new object (a restart) still sees today's spend.
    assert GnaniBudget(path, 1, clock).remaining() == 0
    clock.now += timedelta(minutes=2)  # 00:01 UTC the next day
    assert GnaniBudget(path, 1, clock).remaining() == 1


def test_budget_uses_utc_not_the_local_zone(tmp_path: Path) -> None:
    clock = Clock()
    # 23:30 UTC is already the next day in India (UTC+5:30); the counter must still say Nov 2.
    clock.now = datetime(2026, 11, 2, 23, 30, tzinfo=UTC).astimezone(
        timezone(timedelta(hours=5, minutes=30))
    )
    budget = GnaniBudget(tmp_path / "b.json", 5, clock)
    budget.spend()
    assert json.loads((tmp_path / "b.json").read_text("utf-8"))["day"] == "2026-11-02"


def test_corrupt_budget_file_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    path.write_text("{not json", "utf-8")
    with pytest.raises(LiveSpeechUnavailable):
        GnaniBudget(path, 100, Clock()).spend()


def test_unwritable_budget_location_fails_closed(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", "utf-8")
    with pytest.raises(LiveSpeechUnavailable):
        GnaniBudget(blocker / "b.json", 100, Clock()).spend()


def test_zero_budget_disables_live_calls(tmp_path: Path) -> None:
    gate = LiveGate(GnaniBudget(tmp_path / "b.json", 0, Clock()), False, None)
    assert gate.live() is False
    with pytest.raises(LiveSpeechUnavailable):
        gate()


def test_kill_env_blocks_without_spending(tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    gate = LiveGate(GnaniBudget(path, 5, Clock()), True, None)
    with pytest.raises(LiveSpeechUnavailable) as caught:
        gate()
    assert caught.value.reason == "kill_switch"
    assert not path.exists()


def test_kill_file_takes_effect_without_a_restart(tmp_path: Path) -> None:
    kill = tmp_path / "STOP"
    gate = LiveGate(GnaniBudget(tmp_path / "b.json", 5, Clock()), False, kill)
    gate()
    kill.write_text("", "utf-8")
    with pytest.raises(LiveSpeechUnavailable):
        gate()
    kill.unlink()
    gate()
    assert gate.live() is True


@respx.mock
async def test_gate_counts_every_attempt_including_the_retry(tmp_path: Path) -> None:
    route = respx.post(f"{BASE}{STT_PATH}").mock(return_value=httpx.Response(500))
    gate = LiveGate(GnaniBudget(tmp_path / "b.json", 10, Clock()), False, None)
    client = GnaniClient(
        Settings(gnani_api_key=SecretStr("k"), gnani_base_url=BASE),
        retry_wait_s=0,
        before_attempt=gate,
    )
    with pytest.raises(GnaniError):
        await client.transcribe(b"RIFF", "a.wav", "bn-IN")
    assert route.call_count == 2
    assert GnaniBudget(tmp_path / "b.json", 10, Clock()).remaining() == 8


@respx.mock
async def test_exhausted_budget_sends_no_request(tmp_path: Path) -> None:
    route = respx.post(f"{BASE}{STT_PATH}").mock(
        return_value=httpx.Response(200, json={"success": True, "transcript": "x"})
    )
    gate = LiveGate(GnaniBudget(tmp_path / "b.json", 0, Clock()), False, None)
    client = GnaniClient(
        Settings(gnani_api_key=SecretStr("k"), gnani_base_url=BASE), before_attempt=gate
    )
    with pytest.raises(LiveSpeechUnavailable):
        await client.transcribe(b"RIFF", "a.wav", "bn-IN")
    assert route.call_count == 0


@respx.mock
async def test_client_without_a_gate_behaves_as_before() -> None:
    respx.post(f"{BASE}{STT_PATH}").mock(
        return_value=httpx.Response(200, json={"success": True, "transcript": "ok"})
    )
    client = GnaniClient(Settings(gnani_api_key=SecretStr("k"), gnani_base_url=BASE))
    assert await client.transcribe(b"RIFF", "a.wav", "bn-IN") == "ok"


def test_empty_kill_file_variable_means_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAATHI_KILL_FILE", "")
    assert Settings(gnani_api_key=SecretStr("k")).kill_file is None


def test_bundle_loader_rejects_other_versions_and_skips_missing_audio(tmp_path: Path) -> None:
    turn = {
        "clip_sha256": "a" * 64,
        "src": "en",
        "tgt": "kn",
        "transcript": "t",
        "translation": "x",
        "verified": True,
        "audio": "gone.wav",
    }
    path = tmp_path / BUNDLE_NAME
    path.write_text(json.dumps({"version": 99, "turns": [turn]}), "utf-8")
    assert load_bundle(tmp_path) is None
    path.write_text(json.dumps({"version": BUNDLE_VERSION, "turns": [turn]}), "utf-8")
    assert load_bundle(tmp_path) is None  # its only audio file is missing
