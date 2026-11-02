"""Public mode wired into the app: client IP, room limits, upload cap, paused live mode, healthz
and the zero-call guided demo. Gnani is always a fake; no network is used."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr

from saathi.app import create_app
from saathi.config import Settings
from saathi.demobundle import BUNDLE_NAME, BUNDLE_VERSION, clip_digest
from saathi.gnani import GnaniClient, LiveSpeechUnavailable
from test_room_api import FakeGnani, FakeTranslator, auth, make_room, post_turn
from wavs import make_wav

TRANSCRIPT = "gate number 2 near the blue temple"


class NoGnani:
    """Any use at all is a test failure: the guided demo must never reach Gnani."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Gnani was touched: {name}")


class PausedGnani(FakeGnani):
    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        raise LiveSpeechUnavailable("budget")

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        raise LiveSpeechUnavailable("budget")


def public_settings(**overrides: Any) -> Settings:
    fields: dict[str, Any] = {
        "gnani_api_key": SecretStr("k"),
        "public_mode": True,
        "trusted_proxies": "127.0.0.1",
        "budget_file": Path("unused-budget.json"),
        "demo_bundle_dir": Path("unused-bundle"),
        "room_rate_limit_per_minute": 100,
        "turn_rate_limit_per_minute": 100,
        "reply_rate_limit_per_minute": 100,
    }
    fields.update(overrides)
    return Settings(**fields)


def make_client(settings: Settings, gnani: Any) -> httpx.AsyncClient:
    app = create_app(settings, cast(GnaniClient, gnani), FakeTranslator())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://saathi")


def write_bundle(directory: Path, clip: bytes, src: str = "en", tgt: str = "kn") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "turn.wav").write_bytes(make_wav(0.5))
    turn = {
        "clip_sha256": clip_digest(clip),
        "src": src,
        "tgt": tgt,
        "transcript": TRANSCRIPT,
        "translation": "stored translation",
        "verified": True,
        "audio": "turn.wav",
    }
    (directory / BUNDLE_NAME).write_text(
        json.dumps({"version": BUNDLE_VERSION, "turns": [turn]}), encoding="utf-8"
    )


@pytest.fixture
async def spoof_client() -> AsyncIterator[httpx.AsyncClient]:
    settings = public_settings(room_rate_limit_per_minute=1)
    async with make_client(settings, FakeGnani()) as client:
        yield client


async def test_trusted_proxy_gives_each_forwarded_client_its_own_limit(
    spoof_client: httpx.AsyncClient,
) -> None:
    for ip in ("198.51.100.1", "198.51.100.2"):
        response = await spoof_client.post(
            "/rooms", json={"language": "en"}, headers={"X-Forwarded-For": ip}
        )
        assert response.status_code == 201
    again = await spoof_client.post(
        "/rooms", json={"language": "en"}, headers={"X-Forwarded-For": "198.51.100.1"}
    )
    assert again.status_code == 429


async def test_forged_forwarded_header_from_an_untrusted_peer_does_not_dodge_the_limit() -> None:
    # The test peer is 127.0.0.1, which is not trusted here, so the header must be ignored.
    settings = public_settings(trusted_proxies="10.0.0.0/8", room_rate_limit_per_minute=1)
    async with make_client(settings, FakeGnani()) as client:
        first = await client.post(
            "/rooms", json={"language": "en"}, headers={"X-Forwarded-For": "198.51.100.1"}
        )
        second = await client.post(
            "/rooms", json={"language": "en"}, headers={"X-Forwarded-For": "198.51.100.2"}
        )
    assert (first.status_code, second.status_code) == (201, 429)


async def test_local_mode_ignores_the_forwarded_header_even_from_loopback() -> None:
    settings = Settings(
        gnani_api_key=SecretStr("k"), room_rate_limit_per_minute=1, trusted_proxies="127.0.0.1"
    )
    async with make_client(settings, FakeGnani()) as client:
        first = await client.post(
            "/rooms", json={"language": "en"}, headers={"X-Forwarded-For": "198.51.100.1"}
        )
        second = await client.post(
            "/rooms", json={"language": "en"}, headers={"X-Forwarded-For": "198.51.100.2"}
        )
    assert (first.status_code, second.status_code) == (201, 429)


async def test_hourly_room_creation_cap_per_ip() -> None:
    async with make_client(public_settings(room_creates_per_hour=2), FakeGnani()) as client:
        codes = [
            (await client.post("/rooms", json={"language": "en"})).status_code for _ in range(3)
        ]
    assert codes == [201, 201, 429]


async def test_public_room_cap_is_enforced() -> None:
    async with make_client(public_settings(public_max_rooms=1), FakeGnani()) as client:
        first = await client.post("/rooms", json={"language": "en"})
        second = await client.post(
            "/rooms", json={"language": "en"}, headers={"X-Forwarded-For": "198.51.100.9"}
        )
    assert (first.status_code, second.status_code) == (201, 503)


async def test_public_upload_cap_rejects_before_any_paid_call() -> None:
    gnani = FakeGnani()
    async with make_client(public_settings(max_upload_bytes=1000), gnani) as client:
        room = await make_room(client)
        big = await post_turn(client, room, make_wav(1.0))  # 32 kB
    assert big.status_code == 413
    assert gnani.stt_calls == 0


async def test_local_mode_keeps_the_default_upload_limit() -> None:
    settings = Settings(gnani_api_key=SecretStr("k"), max_upload_bytes=1000)
    async with make_client(settings, FakeGnani()) as client:
        room = await make_room(client)
        assert (await post_turn(client, room, make_wav(1.0))).status_code == 200


async def test_paused_live_mode_returns_a_clean_503_not_a_gnani_error() -> None:
    async with make_client(public_settings(), PausedGnani()) as client:
        room = await make_room(client)
        response = await post_turn(client, room)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "live_paused"
    assert "guided demo" in detail["message_en"]


async def test_quick_reply_text_still_flows_when_live_audio_is_paused() -> None:
    async with make_client(public_settings(), PausedGnani()) as client:
        room = await make_room(client, "en", "kn")
        replied = await client.post(
            f"/rooms/{room['code']}/quick-reply",
            json={"phrase_id": "coming"},
            headers=auth(room["rider"]),
        )
    assert replied.status_code in (204, 422)  # 422 only if the id is not a rider phrase


async def test_healthz_is_unchanged_locally_and_reports_live_state_when_public(
    tmp_path: Path,
) -> None:
    async with make_client(Settings(gnani_api_key=SecretStr("k")), FakeGnani()) as local:
        assert (await local.get("/healthz")).json() == {"status": "ok"}
    on = public_settings(budget_file=tmp_path / "b.json")
    async with make_client(on, FakeGnani()) as client:
        assert (await client.get("/healthz")).json() == {"status": "ok", "live": True}
    off = public_settings(budget_file=tmp_path / "b.json", kill_switch=True)
    async with make_client(off, FakeGnani()) as client:
        assert (await client.get("/healthz")).json() == {"status": "ok", "live": False}


async def test_guided_demo_replays_a_stored_turn_with_zero_gnani_calls(tmp_path: Path) -> None:
    clip = make_wav(0.7)
    write_bundle(tmp_path, clip)
    settings = public_settings(demo_bundle_dir=tmp_path, demo_clips_dir=tmp_path / "clips")
    async with make_client(settings, NoGnani()) as client:
        assert (await client.get("/features")).json() == {"demo_input": True}
        room = await make_room(client, "en", "kn")
        response = await client.post(
            f"/rooms/{room['code']}/turn",
            files={"audio": ("a.wav", clip, "audio/wav")},
            headers={**auth(room["customer"]), "X-Demo-Clip": "1"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert body["facts"], "chips are recomputed locally from the stored transcript"
    assert body["timings"]["total_ms"] == 0


async def test_guided_demo_refuses_an_unknown_clip_instead_of_going_live(tmp_path: Path) -> None:
    write_bundle(tmp_path, make_wav(0.7))
    settings = public_settings(demo_bundle_dir=tmp_path, demo_clips_dir=tmp_path / "clips")
    async with make_client(settings, NoGnani()) as client:
        room = await make_room(client, "en", "kn")
        response = await client.post(
            f"/rooms/{room['code']}/turn",
            files={"audio": ("a.wav", make_wav(0.9), "audio/wav")},
            headers={**auth(room["customer"]), "X-Demo-Clip": "1"},
        )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "demo_no_match"


async def test_guided_demo_does_not_match_the_wrong_language_pair(tmp_path: Path) -> None:
    clip = make_wav(0.7)
    write_bundle(tmp_path, clip, src="en", tgt="kn")
    settings = public_settings(demo_bundle_dir=tmp_path, demo_clips_dir=tmp_path / "clips")
    async with make_client(settings, NoGnani()) as client:
        room = await make_room(client, "en", "hi")
        response = await client.post(
            f"/rooms/{room['code']}/turn",
            files={"audio": ("a.wav", clip, "audio/wav")},
            headers={**auth(room["customer"]), "X-Demo-Clip": "1"},
        )
    assert response.status_code == 422


async def test_without_the_demo_header_the_same_clip_goes_to_the_live_path(
    tmp_path: Path,
) -> None:
    clip = make_wav(0.7)
    write_bundle(tmp_path, clip)
    gnani = FakeGnani()
    settings = public_settings(demo_bundle_dir=tmp_path, demo_clips_dir=tmp_path / "clips")
    async with make_client(settings, gnani) as client:
        room = await make_room(client, "en", "kn")
        assert (await post_turn(client, room, clip)).status_code == 200
    assert gnani.stt_calls == 1


async def test_public_mode_without_a_bundle_offers_no_demo() -> None:
    async with make_client(public_settings(), FakeGnani()) as client:
        assert (await client.get("/features")).json() == {"demo_input": False}


async def test_invalid_bundle_is_ignored_not_fatal(tmp_path: Path) -> None:
    (tmp_path / BUNDLE_NAME).write_text("{broken", encoding="utf-8")
    async with make_client(public_settings(demo_bundle_dir=tmp_path), FakeGnani()) as client:
        assert (await client.get("/features")).json() == {"demo_input": False}


async def test_qr_encodes_the_public_origin_and_the_rider_page_only() -> None:
    settings = public_settings(public_base_url="https://saathi.example")
    async with make_client(settings, FakeGnani()) as client:
        room = await make_room(client, "en", "kn")
        response = await client.get(f"/rooms/{room['code']}/qr.svg", headers=auth(room["customer"]))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.headers["cache-control"] == "no-store"
    assert response.content.lstrip().startswith(b"<svg")
    assert room["customer"].encode() not in response.content


async def test_qr_needs_a_room_token_so_it_cannot_probe_codes() -> None:
    async with make_client(public_settings(), FakeGnani()) as client:
        room = await make_room(client, "en", "kn")
        anonymous = await client.get(f"/rooms/{room['code']}/qr.svg")
        wrong = await client.get(f"/rooms/{room['code']}/qr.svg", headers=auth("not-a-token"))
        unknown = await client.get("/rooms/ABCDEF/qr.svg", headers=auth(room["customer"]))
    assert (anonymous.status_code, wrong.status_code, unknown.status_code) == (404, 404, 404)


@pytest.mark.parametrize("value", ["https://host/path", "javascript:alert(1)", "host.example"])
def test_a_public_base_url_must_be_a_bare_origin(value: str) -> None:
    with pytest.raises(ValueError):
        public_settings(public_base_url=value)


def test_an_empty_public_base_url_means_unset() -> None:
    assert public_settings(public_base_url="").public_base_url is None
