"""Failure injection: when a stage fails mid-turn, the API says so and the listener sees nothing.

A turn publishes only after STT, translation and TTS have all succeeded, so every failure
below must leave the room exactly as it was: no event on either stream, no card change, no
catch-up entry for a reconnect, no stored audio.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr

from placeholders import carry
from saathi.app import create_app
from saathi.config import Settings
from saathi.gnani import GnaniClient, GnaniError
from saathi.rooms import Event, Role, Room, RoomManager
from saathi.unavailable import translation_unavailable_text, unavailable_text
from wavs import make_wav, require_speech_audio

SEED_TRANSCRIPT = "gate number 2 near the blue temple"  # synthetic
NEW_TRANSCRIPT = "gate number 9 near the red shop"  # what a failing turn would have said
UPSTREAM_DETAIL = "upstream-body-with-secret-detail"  # must never reach a client


class FakeGnani:
    def __init__(self) -> None:
        self.transcript = SEED_TRANSCRIPT
        self.stt_error: GnaniError | None = None
        self.tts_error: GnaniError | None = None
        self.stt_calls = 0
        self.tts_calls = 0

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        self.stt_calls += 1
        require_speech_audio(audio)
        if self.stt_error:
            raise self.stt_error
        return self.transcript

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        self.tts_calls += 1
        if self.tts_error:
            raise self.tts_error
        return b"RIFFfake-speech"

    async def aclose(self) -> None:
        return None


class FakeTranslator:
    def __init__(self) -> None:
        self.error: Exception | None = None

    def translate(self, text: str, src: str, tgt: str) -> str:
        if self.error:
            raise self.error
        return carry("kannada text", text)


@dataclass
class Env:
    client: httpx.AsyncClient
    gnani: FakeGnani
    translator: FakeTranslator
    manager: RoomManager
    room: Room
    tokens: dict[Role, str]
    code: str
    queues: dict[Role, asyncio.Queue[Event | None]]

    async def turn(self, who: Role) -> httpx.Response:
        return await self.client.post(
            f"/rooms/{self.code}/turn",
            files={"audio": ("a.wav", make_wav(), "audio/wav")},
            headers={"Authorization": f"Bearer {self.tokens[who]}"},
        )

    def untouched(self) -> tuple[Any, ...]:
        """Everything a failed turn must not change."""
        return (
            dict(self.room.card.entries),
            dict(self.room.catch_up),
            list(self.room.audio),
            [q.empty() for q in self.queues.values()],
        )


@pytest.fixture
async def env() -> AsyncIterator[Env]:
    gnani, translator, manager = FakeGnani(), FakeTranslator(), RoomManager(max_rooms=3)
    settings = Settings(gnani_api_key=SecretStr("k"))
    app = create_app(settings, cast(GnaniClient, gnani), translator, manager)
    # A turn that raises must come back as a response, as it does under a real server.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://saathi") as client:
        created = (await client.post("/rooms", json={"language": "en"})).json()
        code = created["code"]
        joined = (await client.post(f"/rooms/{code}/join", json={"language": "kn"})).json()
        tokens: dict[Role, str] = {"customer": created["token"], "rider": joined["token"]}
        room = manager.authorize(created["code"], tokens["customer"]).room
        e = Env(client, gnani, translator, manager, room, tokens, created["code"], {})
        assert (await e.turn("customer")).status_code == 200  # a card with gate 2 to protect
        e.queues = {role: manager.subscribe(room, role) for role in ("customer", "rider")}
        gnani.stt_calls = gnani.tts_calls = 0
        yield e


def _stt(status: int) -> GnaniError:
    return GnaniError(UPSTREAM_DETAIL, status)


FAILURES = [
    pytest.param("stt_error", _stt(0), 502, "speech_unavailable", id="stt-timeout"),
    pytest.param("stt_error", _stt(503), 502, "speech_unavailable", id="stt-5xx"),
    pytest.param("stt_error", _stt(429), 503, None, id="stt-429"),
    pytest.param("tts_error", _stt(0), 502, "speech_unavailable", id="tts-timeout"),
    pytest.param("tts_error", _stt(500), 502, "speech_unavailable", id="tts-5xx-after-stt"),
    pytest.param("tts_error", _stt(429), 503, None, id="tts-429-after-stt"),
]


@pytest.mark.parametrize("who", ["customer", "rider"])
@pytest.mark.parametrize(("attr", "error", "status", "code"), FAILURES)
async def test_a_gnani_failure_is_reported_and_the_room_is_untouched(
    env: Env, who: Role, attr: str, error: GnaniError, status: int, code: str | None
) -> None:
    env.gnani.transcript = NEW_TRANSCRIPT
    setattr(env.gnani, attr, error)
    before = env.untouched()

    response = await env.turn(who)

    assert response.status_code == status
    assert UPSTREAM_DETAIL not in response.text
    if code:
        detail = response.json()["detail"]
        speaker_language = env.room.participants[who].language
        assert detail == {
            "code": code,
            "message": unavailable_text(speaker_language),
            "message_en": unavailable_text("en"),
        }
    assert env.untouched() == before
    assert env.gnani.stt_calls == 1


async def test_a_tts_failure_happens_after_a_successful_stt_and_translation(env: Env) -> None:
    env.gnani.transcript = NEW_TRANSCRIPT
    env.gnani.tts_error = _stt(500)
    await env.turn("customer")
    assert (env.gnani.stt_calls, env.gnani.tts_calls) == (1, 1)
    assert env.room.card.entries["gate"].fact.value == "2"  # the facts were found but not applied


@pytest.mark.parametrize("transcript", ["", "   \n"])
async def test_an_empty_transcript_is_no_speech_and_costs_no_tts(
    env: Env, transcript: str
) -> None:
    env.gnani.transcript = transcript
    before = env.untouched()

    response = await env.turn("customer")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "no_speech"
    assert env.untouched() == before
    assert env.gnani.tts_calls == 0


async def test_a_garbage_transcript_gives_no_facts_and_no_card_change(env: Env) -> None:
    env.gnani.transcript = "qwerty zxcv asdf ::: ~~~"

    response = await env.turn("customer")

    assert response.status_code == 200
    assert response.json()["facts"] == []
    assert env.room.card.entries["gate"].fact.value == "2"
    assert env.queues["customer"].empty()  # no card event: nothing was learned
    turn = env.queues["rider"].get_nowait()
    assert turn is not None and turn.name == "turn" and turn.data["facts"] == []
    assert env.queues["rider"].empty()


@pytest.mark.parametrize("who", ["customer", "rider"])
async def test_a_translation_exception_is_a_localized_502_and_the_room_is_untouched(
    env: Env, who: Role
) -> None:
    env.gnani.transcript = NEW_TRANSCRIPT
    env.translator.error = RuntimeError(UPSTREAM_DETAIL)
    before = env.untouched()

    response = await env.turn(who)

    assert response.status_code == 502
    assert UPSTREAM_DETAIL not in response.text
    speaker_language = env.room.participants[who].language
    assert response.json()["detail"] == {
        "code": "translation_unavailable",
        "message": translation_unavailable_text(speaker_language),
        "message_en": translation_unavailable_text("en"),
    }
    assert env.untouched() == before
    assert env.gnani.tts_calls == 0  # nothing was spoken for a sentence that never existed


async def test_the_room_works_again_after_a_failed_turn(env: Env) -> None:
    env.gnani.transcript = NEW_TRANSCRIPT
    env.gnani.stt_error = _stt(503)
    assert (await env.turn("customer")).status_code == 502
    env.gnani.stt_error = None

    assert (await env.turn("customer")).status_code == 200

    entry = env.room.card.entries["gate"]
    assert (entry.fact.value, entry.previous) == ("9", "2")
