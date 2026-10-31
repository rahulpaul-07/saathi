import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import httpx
import pytest
from pydantic import SecretStr

from saathi.app import create_app
from saathi.config import Settings
from saathi.demo import load_demo_clips
from saathi.gnani import GnaniClient
from saathi.rooms import RoomManager
from test_room_api import FakeGnani, FakeTranslator, auth, make_room
from wavs import make_wav


def write_clips(directory: Path, clips: list[dict[str, str]], files: list[str]) -> None:
    (directory / "manifest.json").write_text(json.dumps({"clips": clips}), encoding="utf-8")
    for name in files:
        (directory / f"{name}.wav").write_bytes(make_wav())


def make_client(manager: RoomManager, demo_dir: Path | None) -> httpx.AsyncClient:
    settings = Settings(
        gnani_api_key=SecretStr("k"),
        demo_input=demo_dir is not None,
        demo_clips_dir=demo_dir or Path("unused"),
    )
    app = create_app(settings, cast(GnaniClient, FakeGnani()), FakeTranslator(), manager)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://saathi")


@pytest.fixture
async def off(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(RoomManager(max_rooms=3), None) as client:
        yield client


@pytest.fixture
async def on(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    write_clips(
        tmp_path,
        [
            {"id": "kn-gate", "lang": "kn", "label": "Gate 2"},
            {"id": "ta-gone", "lang": "ta", "label": "file is missing"},
            {"id": "xx-lang", "lang": "xx", "label": "unsupported language"},
        ],
        ["kn-gate", "xx-lang"],
    )
    async with make_client(RoomManager(max_rooms=3), tmp_path) as client:
        yield client


async def test_demo_is_off_by_default_and_exposes_nothing(off: httpx.AsyncClient) -> None:
    assert Settings(gnani_api_key=SecretStr("k")).demo_input is False
    assert (await off.get("/features")).json() == {"demo_input": False}
    assert (await off.get("/demo/clips")).status_code == 404
    assert (await off.get("/demo/clips/kn-gate.wav")).status_code == 404


async def test_demo_lists_and_serves_only_manifest_clips_with_a_file(
    on: httpx.AsyncClient,
) -> None:
    assert (await on.get("/features")).json() == {"demo_input": True}
    listed = (await on.get("/demo/clips")).json()
    assert listed == [{"id": "kn-gate", "lang": "kn", "label": "Gate 2", "label_local": ""}]
    audio = await on.get("/demo/clips/kn-gate.wav")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"
    assert audio.content == make_wav()


@pytest.mark.parametrize("clip_id", ["ta-gone", "unknown", "..%2Fmanifest", "UPPER", "a" * 60])
async def test_demo_refuses_ids_outside_the_manifest(on: httpx.AsyncClient, clip_id: str) -> None:
    assert (await on.get(f"/demo/clips/{clip_id}.wav")).status_code in {404, 422}


def test_broken_or_missing_manifest_offers_no_clips(tmp_path: Path) -> None:
    assert load_demo_clips(tmp_path) == {}
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    assert load_demo_clips(tmp_path) == {}
    (tmp_path / "manifest.json").write_text('{"clips": [{"id": 1}]}', encoding="utf-8")
    assert load_demo_clips(tmp_path) == {}


async def send_turn(client: httpx.AsyncClient, manager: RoomManager, marker: str | None) -> object:
    room = await make_room(client)
    queue = manager.subscribe(manager.authorize(room["code"], room["rider"]).room, "rider")
    headers = {**auth(room["customer"]), **({"X-Demo-Clip": marker} if marker else {})}
    sent = await client.post(
        f"/rooms/{room['code']}/turn",
        files={"audio": ("a.wav", make_wav(), "audio/wav")},
        headers=headers,
    )
    assert sent.status_code == 200
    event = queue.get_nowait()
    assert event is not None
    return event.data["demo_clip"]


async def test_listener_is_told_a_turn_was_a_demo_clip_only_when_demo_is_on(
    tmp_path: Path,
) -> None:
    write_clips(tmp_path, [], [])
    manager = RoomManager(max_rooms=3)
    async with make_client(manager, tmp_path) as client:
        assert await send_turn(client, manager, "1") is True
        assert await send_turn(client, manager, None) is False
    manager = RoomManager(max_rooms=3)
    async with make_client(manager, None) as client:
        assert await send_turn(client, manager, "1") is False  # header ignored when off
