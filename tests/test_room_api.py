import asyncio
import itertools
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr

from placeholders import carry
from saathi.app import create_app
from saathi.audio import MAX_AUDIO_BYTES
from saathi.config import Settings
from saathi.gnani import GnaniClient, GnaniError
from saathi.labels import chip_label
from saathi.languages import LANGUAGES
from saathi.quickreplies import IDS_BY_ROLE, QUICK_REPLIES
from saathi.repeatprompts import REPEAT_PROMPTS
from saathi.rooms import Event, Role, RoomManager, other
from saathi.unavailable import UNAVAILABLE
from wavs import make_wav

TRANSCRIPT = "gate number 2 near the blue temple"  # synthetic
TRANSLATION = "kannada text"


class FakeGnani:
    def __init__(self) -> None:
        self.transcript = TRANSCRIPT
        self.error: GnaniError | None = None
        self.stt_calls = 0

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        self.stt_calls += 1
        if self.error:
            raise self.error
        return self.transcript

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        return b"RIFFfake-speech"

    async def aclose(self) -> None:
        return None


class FakeTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return carry(TRANSLATION, text)


@pytest.fixture
def gnani() -> FakeGnani:
    return FakeGnani()


@pytest.fixture
def manager() -> RoomManager:
    return RoomManager(max_rooms=3)


def build_client(
    gnani: FakeGnani,
    manager: RoomManager,
    room_limit: int = 100,
    turn_limit: int = 100,
    reply_limit: int = 100,
) -> httpx.AsyncClient:
    settings = Settings(
        gnani_api_key=SecretStr("k"),
        room_rate_limit_per_minute=room_limit,
        turn_rate_limit_per_minute=turn_limit,
        reply_rate_limit_per_minute=reply_limit,
    )
    app = create_app(settings, cast(GnaniClient, gnani), FakeTranslator(), manager)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://saathi")


@pytest.fixture
async def client(gnani: FakeGnani, manager: RoomManager) -> AsyncIterator[httpx.AsyncClient]:
    async with build_client(gnani, manager) as c:
        yield c


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make_room(client: httpx.AsyncClient, src: str = "en", tgt: str = "kn") -> dict[str, Any]:
    created = await client.post("/rooms", json={"language": src})
    assert created.status_code == 201
    code = created.json()["code"]
    joined = await client.post(f"/rooms/{code}/join", json={"language": tgt})
    assert joined.status_code == 200
    return {"code": code, "customer": created.json()["token"], "rider": joined.json()["token"]}


async def post_turn(
    client: httpx.AsyncClient,
    room: dict[str, Any],
    audio: bytes | None = None,
    who: str = "customer",
    content_type: str = "audio/wav",
) -> httpx.Response:
    return await client.post(
        f"/rooms/{room['code']}/turn",
        files={"audio": ("a.wav", make_wav() if audio is None else audio, content_type)},
        headers=auth(room[who]),
    )


async def test_create_and_join_return_roles_and_languages(client: httpx.AsyncClient) -> None:
    created = (await client.post("/rooms", json={"language": "en"})).json()
    assert created["role"] == "customer" and created["peer_language"] is None
    joined = (await client.post(f"/rooms/{created['code']}/join", json={"language": "kn"})).json()
    assert joined["role"] == "rider"
    assert joined["peer_language"] == "en"
    assert joined["token"] != created["token"]


@pytest.mark.parametrize(
    "body", [{"language": "ur"}, {"language": ""}, {}, {"language": "en", "x": 1}]
)
async def test_create_rejects_bad_body(client: httpx.AsyncClient, body: dict[str, Any]) -> None:
    assert (await client.post("/rooms", json=body)).status_code == 422


@pytest.mark.parametrize("code", ["abc123", "ABCDE", "ABCDEFG", "ABCDE0", "ABCDEI"])
async def test_malformed_room_code_is_rejected(client: httpx.AsyncClient, code: str) -> None:
    assert (await client.post(f"/rooms/{code}/join", json={"language": "kn"})).status_code == 422


async def test_third_joiner_is_refused(client: httpx.AsyncClient) -> None:
    room = await make_room(client)
    response = await client.post(f"/rooms/{room['code']}/join", json={"language": "hi"})
    assert response.status_code == 409


async def test_join_unknown_room_and_same_language(client: httpx.AsyncClient) -> None:
    assert (await client.post("/rooms/ABCDEF/join", json={"language": "kn"})).status_code == 404
    code = (await client.post("/rooms", json={"language": "en"})).json()["code"]
    assert (await client.post(f"/rooms/{code}/join", json={"language": "en"})).status_code == 400


async def test_join_attempts_are_rate_limited_per_ip(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager, room_limit=3) as limited:
        statuses = [
            (await limited.post("/rooms/ABCDEF/join", json={"language": "kn"})).status_code
            for _ in range(4)
        ]
    assert statuses == [404, 404, 404, 429]  # guesses count even when the room does not exist


async def test_room_cap_returns_503(client: httpx.AsyncClient) -> None:
    for _ in range(3):
        assert (await client.post("/rooms", json={"language": "en"})).status_code == 201
    assert (await client.post("/rooms", json={"language": "en"})).status_code == 503


async def test_turn_returns_facts_and_pushes_translation_to_the_rider(
    client: httpx.AsyncClient, manager: RoomManager
) -> None:
    room = await make_room(client)
    rider_queue = manager.subscribe(manager.authorize(room["code"], room["rider"]).room, "rider")

    response = await post_turn(client, room)

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert {"kind": "gate", "value": "2"}.items() <= body["facts"][0].items()
    assert "start" not in body["facts"][0]
    assert "transcript" not in body and "translation" not in body
    assert set(body["timings"]) == {"stt_ms", "translate_ms", "tts_ms", "total_ms"}
    assert all(isinstance(value, float) and value >= 0 for value in body["timings"].values())

    event = rider_queue.get_nowait()
    assert event is not None and event.name == "turn"
    assert "timings" not in event.data  # the speaker's numbers are not the listener's business
    assert event.data["translation"].startswith(TRANSLATION)
    heard = event.data["facts"][0]
    assert {"kind": "gate", "value": "2"}.items() <= heard.items()
    assert (body["facts"][0]["label"], body["facts"][0]["label_status"]) == ("Gate", "source")
    assert (heard["label"], heard["label_status"]) == (chip_label("gate", "kn").text, "pending")
    assert event.data["src"] == "en" and event.data["tgt"] == "kn"

    audio = await client.get(event.data["audio_path"], headers=auth(room["rider"]))
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    assert audio.content == b"RIFFfake-speech"


class LossyTranslator:
    """Drops every placeholder, so the masked translation fails its check."""

    def translate(self, text: str, src: str, tgt: str) -> str:
        return TRANSLATION


async def test_a_good_turn_does_not_ask_to_repeat(client: httpx.AsyncClient) -> None:
    room = await make_room(client)
    assert (await post_turn(client, room)).json()["repeat"] is None


@pytest.mark.parametrize("language", list(LANGUAGES))
async def test_no_facts_asks_the_speaker_to_repeat_in_their_own_language(
    gnani: FakeGnani, manager: RoomManager, language: str
) -> None:
    gnani.transcript = "okay thank you"  # no gate, floor, cross/main or landmark
    listener = "hi" if language != "hi" else "en"
    client, _ = build_recording_client(gnani, manager)
    async with client:
        room = await make_room(client, src=language, tgt=listener)
        live = manager.authorize(room["code"], room["rider"]).room
        rider_queue = manager.subscribe(live, "rider")
        response = await post_turn(client, room)

    assert response.status_code == 200
    body = response.json()
    expected = REPEAT_PROMPTS[language]["no_facts"]
    assert body["repeat"] == {
        "reason": "no_facts",
        "text": expected.text,
        "review_status": expected.review_status,
    }
    event = rider_queue.get_nowait()
    assert event is not None and "repeat" not in event.data  # the listener is never nagged


async def test_failed_placeholder_check_asks_to_repeat_and_still_delivers_the_facts(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    settings = Settings(gnani_api_key=SecretStr("k"))
    app = create_app(settings, cast(GnaniClient, gnani), LossyTranslator(), manager)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://saathi"
    ) as client:
        room = await make_room(client, src="en", tgt="kn")
        response = await post_turn(client, room)

    body = response.json()
    assert response.status_code == 200 and body["verified"] is False
    assert body["repeat"]["reason"] == "unverified"
    assert body["repeat"]["text"] == REPEAT_PROMPTS["en"]["unverified"].text
    assert {(f["kind"], f["value"]) for f in body["facts"]} >= {("gate", "2")}


@pytest.mark.parametrize("language", list(LANGUAGES))
async def test_a_rider_turn_without_facts_is_not_asked_to_repeat(
    gnani: FakeGnani, manager: RoomManager, language: str
) -> None:
    gnani.transcript = "coming in 2 minutes"  # nothing an address check would find
    customer_lang = "hi" if language != "hi" else "en"
    client, _ = build_recording_client(gnani, manager)
    async with client:
        room = await make_room(client, src=customer_lang, tgt=language)
        response = await post_turn(client, room, who="rider")
    assert response.status_code == 200
    assert response.json()["repeat"] is None


async def test_a_rider_turn_that_fails_the_check_is_asked_to_repeat(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    settings = Settings(gnani_api_key=SecretStr("k"))
    app = create_app(settings, cast(GnaniClient, gnani), LossyTranslator(), manager)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://saathi"
    ) as client:
        room = await make_room(client, src="kn", tgt="en")  # the rider speaks English
        response = await post_turn(client, room, who="rider")

    body = response.json()
    assert response.status_code == 200 and body["verified"] is False
    assert body["repeat"]["reason"] == "unverified"
    assert body["repeat"]["text"] == REPEAT_PROMPTS["en"]["unverified"].text


async def test_turn_before_rider_joins_is_refused_without_a_paid_call(
    client: httpx.AsyncClient, gnani: FakeGnani
) -> None:
    created = (await client.post("/rooms", json={"language": "en"})).json()
    room = {"code": created["code"], "customer": created["token"]}
    assert (await post_turn(client, room)).status_code == 409
    assert gnani.stt_calls == 0


class RecordingTranslator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def translate(self, text: str, src: str, tgt: str) -> str:
        self.calls.append((src, tgt))
        return carry(f"{src}>{tgt}", text)


def build_recording_client(
    gnani: FakeGnani, manager: RoomManager
) -> tuple[httpx.AsyncClient, RecordingTranslator]:
    translator = RecordingTranslator()
    settings = Settings(
        gnani_api_key=SecretStr("k"),
        room_rate_limit_per_minute=1000,
        turn_rate_limit_per_minute=1000,
    )
    app = create_app(settings, cast(GnaniClient, gnani), translator, manager)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://saathi")
    return client, translator


def drain_turns(queue: asyncio.Queue[Event | None]) -> list[Event]:
    events = []
    while not queue.empty():
        event = queue.get_nowait()
        if event is not None and event.name == "turn":
            events.append(event)
    return events


@pytest.mark.parametrize(
    ("customer_lang", "rider_lang"),
    [("en", "kn"), ("ta", "ml"), ("gu", "pa"), ("hi", "bn"), ("te", "mr")],
)
async def test_either_role_speaks_in_their_language_to_the_other(
    gnani: FakeGnani, manager: RoomManager, customer_lang: str, rider_lang: str
) -> None:
    client, translator = build_recording_client(gnani, manager)
    async with client:
        room = await make_room(client, src=customer_lang, tgt=rider_lang)
        live = manager.authorize(room["code"], room["customer"]).room
        queues = {role: manager.subscribe(live, role) for role in ("customer", "rider")}

        by_customer = await post_turn(client, room, who="customer")
        by_rider = await post_turn(client, room, who="rider")

    assert by_customer.status_code == by_rider.status_code == 200
    # Landmark localization adds calls in the same direction as its turn, so compare distinct
    # directions in order of first use.
    assert list(dict.fromkeys(translator.calls)) == [
        (customer_lang, rider_lang),
        (rider_lang, customer_lang),
    ]
    # The sender never receives their own turn; each gets only the other's (card events aside).
    rider_turns, customer_turns = drain_turns(queues["rider"]), drain_turns(queues["customer"])
    assert len(rider_turns) == len(customer_turns) == 1
    to_rider, to_customer = rider_turns[0], customer_turns[0]
    assert (to_rider.data["src"], to_rider.data["tgt"]) == (customer_lang, rider_lang)
    assert (to_customer.data["src"], to_customer.data["tgt"]) == (rider_lang, customer_lang)
    assert to_customer.data["translation"].startswith(f"{rider_lang}>{customer_lang}")


@pytest.mark.parametrize(
    ("language", "transcript"),
    [
        ("kn", "ಗೇಟ್ ನಂಬರ್ ಎರಡು ಹತ್ತಿರ ಬನ್ನಿ"),
        ("hi", "गेट नंबर दो के पास"),
        ("bn", "গেট নম্বর দুই"),
        ("en", "gate number two, third floor"),
        ("ta", "gate number 2"),
    ],
)
async def test_a_rider_turn_gets_the_same_fact_extraction_as_a_customer_turn(
    gnani: FakeGnani, manager: RoomManager, language: str, transcript: str
) -> None:
    client, _ = build_recording_client(gnani, manager)
    gnani.transcript = transcript
    other_lang = "hi" if language != "hi" else "en"
    async with client:
        room = await make_room(client, src=other_lang, tgt=language)  # the rider speaks `language`
        response = await post_turn(client, room, who="rider")
    assert response.status_code == 200
    facts = {(f["kind"], f["value"]) for f in response.json()["facts"]}
    assert ("gate", "2") in facts


async def test_every_ordered_language_pair_works_for_both_speakers(
    gnani: FakeGnani,
) -> None:
    manager = RoomManager(max_rooms=200)
    client, translator = build_recording_client(gnani, manager)
    pairs = list(itertools.permutations(LANGUAGES, 2))
    assert len(pairs) == 90
    async with client:
        for customer_lang, rider_lang in pairs:
            room = await make_room(client, src=customer_lang, tgt=rider_lang)
            assert (await post_turn(client, room, who="customer")).status_code == 200
            assert (await post_turn(client, room, who="rider")).status_code == 200
            manager.close(manager.authorize(room["code"], room["customer"]).room)
    # Landmark localization repeats a turn's direction, so collapse consecutive duplicates.
    directions = [call for call, _ in itertools.groupby(translator.calls)]
    assert directions == [call for a, b in pairs for call in ((a, b), (b, a))]


@pytest.mark.parametrize(
    ("audio", "content_type", "status"),
    [
        (b"not a wav file", "audio/wav", 400),
        (make_wav(61, rate=8000), "audio/wav", 400),
        (b"RIFF" + b"\x00" * MAX_AUDIO_BYTES, "audio/wav", 413),
        (make_wav(), "text/plain", 415),
        (make_wav(), "application/octet-stream", 415),
    ],
    ids=["not-wav", "too-long", "too-large", "text-type", "octet-type"],
)
async def test_bad_audio_is_rejected_before_any_paid_call(
    client: httpx.AsyncClient, gnani: FakeGnani, audio: bytes, content_type: str, status: int
) -> None:
    room = await make_room(client)
    response = await post_turn(client, room, audio=audio, content_type=content_type)
    assert response.status_code == status
    assert gnani.stt_calls == 0


async def test_turn_rate_limit_applies_before_paid_calls(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager, turn_limit=1) as limited:
        room = await make_room(limited)
        statuses = [(await post_turn(limited, room)).status_code for _ in range(2)]
    assert statuses == [200, 429]
    assert gnani.stt_calls == 1


async def test_upstream_errors_are_generic_and_nothing_is_published(
    client: httpx.AsyncClient, gnani: FakeGnani, manager: RoomManager
) -> None:
    room = await make_room(client)
    rider_queue = manager.subscribe(manager.authorize(room["code"], room["rider"]).room, "rider")
    gnani.error = GnaniError("secret upstream body", status=500)

    response = await post_turn(client, room)

    assert response.status_code == 502
    assert "secret" not in response.text
    assert rider_queue.empty()


async def test_upstream_failure_is_reported_in_the_speakers_language(
    client: httpx.AsyncClient, gnani: FakeGnani
) -> None:
    room = await make_room(client, src="kn", tgt="hi")
    gnani.error = GnaniError("down", status=504)

    spoke = (await post_turn(client, room, who="customer")).json()["detail"]
    answered = (await post_turn(client, room, who="rider")).json()["detail"]

    assert spoke == {"code": "speech_unavailable", "message": UNAVAILABLE["kn"].text}
    assert answered["message"] == UNAVAILABLE["hi"].text


async def test_no_speech_does_not_leak_the_transcript(
    client: httpx.AsyncClient, gnani: FakeGnani
) -> None:
    gnani.transcript = " "
    response = await post_turn(client, await make_room(client))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "no_speech"


async def test_quick_reply_is_sent_in_the_recipients_language(
    client: httpx.AsyncClient, manager: RoomManager
) -> None:
    room = await make_room(client, src="hi", tgt="bn")  # customer hi, rider bn
    live = manager.authorize(room["code"], room["customer"]).room
    customer_queue = manager.subscribe(live, "customer")
    rider_queue = manager.subscribe(live, "rider")
    url = f"/rooms/{room['code']}/quick-reply"

    sent = await client.post(url, json={"phrase_id": "reached_gate"}, headers=auth(room["rider"]))
    assert sent.status_code == 204
    event = customer_queue.get_nowait()
    assert event is not None and event.name == "quick_reply"
    assert event.data["text"] == QUICK_REPLIES["hi"]["reached_gate"].text
    assert event.data["review_status"] == "reviewed"
    fetched = await client.get(event.data["audio_path"], headers=auth(room["customer"]))
    assert fetched.status_code == 200 and fetched.content == b"RIFFfake-speech"

    back = await client.post(url, json={"phrase_id": "coming_down"}, headers=auth(room["customer"]))
    assert back.status_code == 204
    to_rider = rider_queue.get_nowait()
    assert to_rider is not None
    assert to_rider.data["text"] == QUICK_REPLIES["bn"]["coming_down"].text
    assert to_rider.data["review_status"] == "reviewed"
    assert customer_queue.empty()


@pytest.mark.parametrize("role", ["customer", "rider"])
@pytest.mark.parametrize("recipient_language", sorted(LANGUAGES))
async def test_every_phrase_of_each_role_exists_in_every_language(
    client: httpx.AsyncClient, manager: RoomManager, role: Role, recipient_language: str
) -> None:
    sender_language = "en" if recipient_language != "en" else "hi"
    languages = {"customer": sender_language, "rider": sender_language}
    recipient = other(role)
    languages[recipient] = recipient_language
    room = await make_room(client, src=languages["customer"], tgt=languages["rider"])
    queue = manager.subscribe(manager.authorize(room["code"], room[role]).room, recipient)
    for phrase_id in IDS_BY_ROLE[role]:
        response = await client.post(
            f"/rooms/{room['code']}/quick-reply",
            json={"phrase_id": phrase_id},
            headers=auth(room[role]),
        )
        assert response.status_code == 204
        event = queue.get_nowait()
        assert event is not None
        assert event.data["text"] == QUICK_REPLIES[recipient_language][phrase_id].text


async def test_a_role_cannot_send_the_other_roles_phrase_or_free_text(
    client: httpx.AsyncClient,
) -> None:
    room = await make_room(client, src="ta", tgt="ml")
    url = f"/rooms/{room['code']}/quick-reply"
    rider_sends_customer_id = await client.post(
        url, json={"phrase_id": "come_to_gate"}, headers=auth(room["rider"])
    )
    customer_sends_rider_id = await client.post(
        url, json={"phrase_id": "reached_gate"}, headers=auth(room["customer"])
    )
    free_text = await client.post(url, json={"phrase_id": "free text"}, headers=auth(room["rider"]))
    assert rider_sends_customer_id.status_code == 422
    assert customer_sends_rider_id.status_code == 422
    assert free_text.status_code == 422


async def test_quick_reply_without_a_peer_is_refused(client: httpx.AsyncClient) -> None:
    created = (await client.post("/rooms", json={"language": "en"})).json()
    response = await client.post(
        f"/rooms/{created['code']}/quick-reply",
        json={"phrase_id": "come_to_gate"},
        headers=auth(created["token"]),
    )
    assert response.status_code == 409


async def test_quick_reply_text_survives_a_tts_failure(
    client: httpx.AsyncClient, gnani: FakeGnani, manager: RoomManager
) -> None:
    room = await make_room(client, src="hi", tgt="en")  # the rider's phrase arrives in Hindi
    queue = manager.subscribe(manager.authorize(room["code"], room["customer"]).room, "customer")

    async def failing(text: str, language: str, voice: str) -> bytes:
        raise GnaniError("down", 502)

    gnani.synthesize = failing  # type: ignore[method-assign]
    response = await client.post(
        f"/rooms/{room['code']}/quick-reply",
        json={"phrase_id": "coming_2_min"},
        headers=auth(room["rider"]),
    )
    assert response.status_code == 204
    event = queue.get_nowait()
    assert event is not None and event.data["audio_path"] is None
    assert event.data["text"] == "बस 2 मिनट"


async def test_catalog_endpoints_list_languages_and_quick_replies(
    client: httpx.AsyncClient,
) -> None:
    languages = (await client.get("/languages")).json()
    assert len(languages) == 10
    assert {"code": "ta", "name": "Tamil", "tier": "beta"} in languages
    table = (await client.get("/quick-replies")).json()
    assert table["ids"] == {
        "rider": ["reached_gate", "which_floor", "coming_2_min"],
        "customer": ["come_to_gate", "coming_down", "leave_at_security"],
    }
    assert set(table["languages"]) == set(LANGUAGES)
    assert table["languages"]["en"]["come_to_gate"]["review_status"] == "source"
    assert table["languages"]["hi"]["reached_gate"]["review_status"] == "reviewed"
    assert table["languages"]["hi"]["come_to_gate"]["review_status"] == "reviewed"
    assert table["languages"]["bn"]["leave_at_security"]["review_status"] == "reviewed"
    assert table["languages"]["ta"]["come_to_gate"]["review_status"] == "pending"
    assert table["languages"]["kn"]["reached_gate"]["review_status"] == "pending"
    for phrases in table["languages"].values():
        assert len(phrases) == 6 and all(p["text"] for p in phrases.values())


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer nope"},
        {"Authorization": "Basic x"},
    ],
    ids=["missing", "empty", "wrong", "scheme"],
)
async def test_bad_or_missing_token_gets_the_same_404_on_every_route(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    room = await make_room(client)
    code = room["code"]
    responses = [
        await client.get(f"/rooms/{code}/events", headers=headers),
        await client.post(
            f"/rooms/{code}/quick-reply", json={"phrase_id": "which_floor"}, headers=headers
        ),
        await client.get(f"/rooms/{code}/turns/{'a' * 22}/audio", headers=headers),
        await client.delete(f"/rooms/{code}", headers=headers),
        await client.post(
            f"/rooms/{code}/turn", files={"audio": ("a.wav", make_wav())}, headers=headers
        ),
    ]
    assert {r.status_code for r in responses} == {404}
    assert {r.text for r in responses} == {'{"detail":"room not found"}'}


async def test_token_from_another_room_cannot_read_or_act(
    client: httpx.AsyncClient, gnani: FakeGnani
) -> None:
    room_a = await make_room(client)
    room_b = await make_room(client)
    turn = await post_turn(client, room_a)
    audio_id = turn.json()["turn_id"]
    wrong = auth(room_b["customer"])

    audio = await client.get(f"/rooms/{room_a['code']}/turns/{audio_id}/audio", headers=wrong)
    events = await client.get(f"/rooms/{room_a['code']}/events", headers=wrong)
    closing = await client.delete(f"/rooms/{room_a['code']}", headers=wrong)
    stolen = await post_turn(client, {"code": room_a["code"], "customer": room_b["customer"]})

    assert [r.status_code for r in (audio, events, closing, stolen)] == [404, 404, 404, 404]
    assert gnani.stt_calls == 1  # only room A's own turn


async def test_audio_from_another_room_is_not_served_even_with_a_valid_own_token(
    client: httpx.AsyncClient,
) -> None:
    room_a = await make_room(client)
    room_b = await make_room(client)
    audio_id = (await post_turn(client, room_a)).json()["turn_id"]
    response = await client.get(
        f"/rooms/{room_b['code']}/turns/{audio_id}/audio", headers=auth(room_b["rider"])
    )
    assert response.status_code == 404


async def test_expired_room_rejects_everything(gnani: FakeGnani) -> None:
    now = [0.0]
    manager = RoomManager(clock=lambda: now[0], idle_ttl_s=60)
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        now[0] += 61
        turn = await post_turn(client, room)
        events = await client.get(f"/rooms/{room['code']}/events", headers=auth(room["rider"]))
        join = await client.post(f"/rooms/{room['code']}/join", json={"language": "hi"})
    assert [turn.status_code, events.status_code, join.status_code] == [404, 404, 404]
    assert gnani.stt_calls == 0


async def test_bad_audio_id_shape_is_rejected(client: httpx.AsyncClient) -> None:
    room = await make_room(client)
    response = await client.get(
        f"/rooms/{room['code']}/turns/..%2f..%2fetc/audio", headers=auth(room["rider"])
    )
    assert response.status_code in (404, 422)


async def test_event_stream_delivers_state_turn_quick_reply_and_closes(
    client: httpx.AsyncClient, manager: RoomManager
) -> None:
    room = await make_room(client)
    live = manager.authorize(room["code"], room["customer"]).room
    rider_stream = asyncio.create_task(
        client.get(f"/rooms/{room['code']}/events", headers=auth(room["rider"]))
    )
    customer_stream = asyncio.create_task(
        client.get(f"/rooms/{room['code']}/events", headers=auth(room["customer"]))
    )
    async with asyncio.timeout(5):
        while not (
            manager.is_subscribed(live, "rider") and manager.is_subscribed(live, "customer")
        ):
            await asyncio.sleep(0)  # yield so the stream tasks can subscribe

        assert (await post_turn(client, room)).status_code == 200
        reply = await client.post(
            f"/rooms/{room['code']}/quick-reply",
            json={"phrase_id": "coming_2_min"},
            headers=auth(room["rider"]),
        )
        assert reply.status_code == 204
        closed = await client.delete(f"/rooms/{room['code']}", headers=auth(room["customer"]))
        assert closed.status_code == 204
        rider_response, customer_response = await asyncio.gather(rider_stream, customer_stream)

    assert rider_response.headers["content-type"].startswith("text/event-stream")
    assert rider_response.headers["cache-control"] == "no-store"
    rider_text, customer_text = rider_response.text, customer_response.text
    assert rider_text.startswith("event: state")
    assert "event: turn" in rider_text and TRANSLATION in rider_text
    assert "event: quick_reply" in customer_text and "coming_2_min" in customer_text
    assert "event: closed" in rider_text and "event: closed" in customer_text


async def read_card_events(queue: asyncio.Queue[Any]) -> list[dict[str, Any]]:
    events = []
    while not queue.empty():
        event = queue.get_nowait()
        if event is not None and event.name == "card":
            events.append(event.data)
    return events


async def test_customer_turns_build_the_card_and_both_sides_get_it_in_their_language(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["customer"]).room
        customer_queue = manager.subscribe(live, "customer")
        rider_queue = manager.subscribe(live, "rider")

        await post_turn(client, room)
        gnani.transcript = "gate number 4 near the blue temple"
        await post_turn(client, room)

        customer_cards = await read_card_events(customer_queue)
        rider_cards = await read_card_events(rider_queue)

    assert len(customer_cards) == len(rider_cards) == 2
    final_customer = {e["fact"]["kind"]: e for e in customer_cards[-1]["entries"]}
    final_rider = {e["fact"]["kind"]: e for e in rider_cards[-1]["entries"]}
    assert final_customer["gate"]["fact"]["value"] == "4"
    assert final_customer["gate"]["previous"] == "2"
    assert final_customer["gate"]["fact"]["label"] == chip_label("gate", "en").text
    assert final_rider["gate"]["fact"]["label"] == chip_label("gate", "kn").text
    assert final_rider["gate"]["previous"] == "2"


async def test_a_rider_turn_never_changes_the_card(gnani: FakeGnani, manager: RoomManager) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["customer"]).room
        await post_turn(client, room)
        before = dict(live.card.entries)
        customer_queue = manager.subscribe(live, "customer")

        gnani.transcript = "gate number 9 near the red shop"
        assert (await post_turn(client, room, who="rider")).status_code == 200

        assert live.card.entries == before
        assert await read_card_events(customer_queue) == []


async def test_a_customer_turn_without_facts_sends_no_card_event(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["rider"]).room
        rider_queue = manager.subscribe(live, "rider")
        gnani.transcript = "okay thank you"
        await post_turn(client, room)
        assert await read_card_events(rider_queue) == []
        assert live.card.entries == {}


async def test_the_state_snapshot_restores_the_card_after_a_reconnect(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["rider"]).room
        await post_turn(client, room)
        stream = asyncio.create_task(
            client.get(f"/rooms/{room['code']}/events", headers=auth(room["rider"]))
        )
        async with asyncio.timeout(5):
            while not manager.is_subscribed(live, "rider"):
                await asyncio.sleep(0)
            await client.delete(f"/rooms/{room['code']}", headers=auth(room["customer"]))
            response = await stream

    state = response.text.split("\n\n")[0]
    assert state.startswith("event: state")
    assert '"card"' in state and '"value": "2"' in state
    assert chip_label("gate", "kn").text in state


async def test_a_reconnecting_listener_catches_up_the_last_turn_and_reply(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["rider"]).room
        # Sent while the rider has no stream open, as when the phone reloads.
        await post_turn(client, room)
        phrase = IDS_BY_ROLE["customer"][0]
        await client.post(
            f"/rooms/{room['code']}/quick-reply",
            json={"phrase_id": phrase},
            headers=auth(room["customer"]),
        )
        stream = asyncio.create_task(
            client.get(f"/rooms/{room['code']}/events", headers=auth(room["rider"]))
        )
        async with asyncio.timeout(5):
            while not manager.is_subscribed(live, "rider"):
                await asyncio.sleep(0)
            snapshot = manager.snapshot(live, "rider").data
            await client.delete(f"/rooms/{room['code']}", headers=auth(room["customer"]))
            await stream

    assert snapshot["last_turn"]["translation"].startswith(TRANSLATION)
    assert snapshot["last_turn"]["audio_path"].startswith(f"/rooms/{room['code']}/turns/")
    assert snapshot["last_reply"]["phrase_id"] == phrase
    # The sender's own screen gets nothing back.
    assert manager.snapshot(live, "customer").data["last_turn"] is None


async def test_the_card_is_wiped_when_the_room_closes(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["customer"]).room
        await post_turn(client, room)
        assert live.card.entries
        await client.delete(f"/rooms/{room['code']}", headers=auth(room["customer"]))
    assert live.card.entries == {}


async def test_the_card_is_wiped_when_the_room_expires(gnani: FakeGnani) -> None:
    now = [0.0]
    manager = RoomManager(clock=lambda: now[0], idle_ttl_s=60)
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["customer"]).room
        await post_turn(client, room)
        assert live.card.entries
        now[0] += 61
        await client.get(f"/rooms/{room['code']}/events", headers=auth(room["rider"]))
    assert live.card.entries == {}


async def test_card_content_is_never_logged(
    gnani: FakeGnani, manager: RoomManager, caplog: pytest.LogCaptureFixture
) -> None:
    gnani.transcript = "gate number 7 near the zebra statue"
    with caplog.at_level("DEBUG"):
        async with build_client(gnani, manager) as client:
            room = await make_room(client)
            await post_turn(client, room)
    assert "zebra" not in caplog.text


async def chip_reply(
    client: httpx.AsyncClient, room: dict[str, Any], body: dict[str, Any], who: str = "rider"
) -> httpx.Response:
    return await client.post(
        f"/rooms/{room['code']}/chip-reply", json=body, headers=auth(room[who])
    )


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "mystery", "action": "confirm"},
        {"kind": "gate", "action": "delete"},
        {"kind": "gate"},
        {"action": "ask"},
        {"kind": "gate", "action": "ask", "text": "free text"},
    ],
)
async def test_chip_reply_schema_rejects_unknown_kinds_actions_and_extras(
    client: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    room = await make_room(client)
    await post_turn(client, room)
    assert (await chip_reply(client, room, body)).status_code == 422


async def test_only_the_rider_can_answer_the_card(
    client: httpx.AsyncClient, manager: RoomManager
) -> None:
    room = await make_room(client)
    live = manager.authorize(room["code"], room["customer"]).room
    await post_turn(client, room)
    response = await chip_reply(client, room, {"kind": "gate", "action": "confirm"}, who="customer")
    assert response.status_code == 403
    assert not live.card.entries["gate"].confirmed


async def test_a_reply_for_a_kind_not_on_the_card_is_rejected(client: httpx.AsyncClient) -> None:
    room = await make_room(client)
    await post_turn(client, room)  # gate, landmark; no floor
    response = await chip_reply(client, room, {"kind": "floor", "action": "confirm"})
    assert response.status_code == 422


async def test_chip_reply_needs_a_valid_token(client: httpx.AsyncClient) -> None:
    room = await make_room(client)
    await post_turn(client, room)
    response = await client.post(
        f"/rooms/{room['code']}/chip-reply",
        json={"kind": "gate", "action": "confirm"},
        headers=auth("wrong"),
    )
    assert response.status_code == 404


async def test_confirm_clears_the_changed_marker_and_both_sides_see_it(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["customer"]).room
        await post_turn(client, room)
        gnani.transcript = "gate number 4 near the blue temple"
        await post_turn(client, room)
        assert live.card.entries["gate"].previous == "2"
        customer_queue = manager.subscribe(live, "customer")
        rider_queue = manager.subscribe(live, "rider")

        response = await chip_reply(client, room, {"kind": "gate", "action": "confirm"})

        assert response.status_code == 204
        for queue in (customer_queue, rider_queue):
            entry = {e["fact"]["kind"]: e for e in (await read_card_events(queue))[-1]["entries"]}
            assert entry["gate"]["confirmed"] is True and entry["gate"]["previous"] is None


async def test_ask_shows_the_question_in_each_viewers_language(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["customer"]).room
        await post_turn(client, room)
        customer_queue = manager.subscribe(live, "customer")
        rider_queue = manager.subscribe(live, "rider")

        await chip_reply(client, room, {"kind": "gate", "action": "ask"})

        customer = (await read_card_events(customer_queue))[-1]["entries"][0]
        rider = (await read_card_events(rider_queue))[-1]["entries"][0]
    assert customer["question"] == f"{chip_label('gate', 'en').text}?"
    assert rider["question"] == f"{chip_label('gate', 'kn').text}?"
    assert customer["confirmed"] is False


async def test_a_new_value_clears_the_confirmation(gnani: FakeGnani, manager: RoomManager) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["customer"]).room
        await post_turn(client, room)
        await chip_reply(client, room, {"kind": "gate", "action": "confirm"})
        assert live.card.entries["gate"].confirmed
        gnani.transcript = "gate number 4 near the blue temple"
        await post_turn(client, room)
    gate = live.card.entries["gate"]
    assert (gate.confirmed, gate.previous) == (False, "2")


async def test_confirmation_state_survives_a_reconnect(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["rider"]).room
        await post_turn(client, room)
        await chip_reply(client, room, {"kind": "gate", "action": "confirm"})
        await chip_reply(client, room, {"kind": "landmark", "action": "ask"})
        stream = asyncio.create_task(
            client.get(f"/rooms/{room['code']}/events", headers=auth(room["customer"]))
        )
        async with asyncio.timeout(5):
            while not manager.is_subscribed(live, "customer"):
                await asyncio.sleep(0)
            await client.delete(f"/rooms/{room['code']}", headers=auth(room["customer"]))
            response = await stream

    state = response.text.split("\n\n")[0]
    assert '"confirmed": true' in state
    assert f'"question": "{chip_label("landmark", "en").text}?"' in state


async def test_chip_replies_are_never_logged(
    gnani: FakeGnani, manager: RoomManager, caplog: pytest.LogCaptureFixture
) -> None:
    gnani.transcript = "gate number 7 near the zebra statue"
    with caplog.at_level("DEBUG"):
        async with build_client(gnani, manager) as client:
            room = await make_room(client)
            await post_turn(client, room)
            await chip_reply(client, room, {"kind": "gate", "action": "ask"})
            await chip_reply(client, room, {"kind": "gate", "action": "confirm"})
    app_logs = [r.getMessage() for r in caplog.records if r.name.startswith("saathi")]
    assert not any("zebra" in m or "confirm" in m or "ask" in m.split() for m in app_logs)
    assert "zebra" not in caplog.text


def test_the_reply_limit_defaults_to_30_per_minute() -> None:
    assert Settings(gnani_api_key=SecretStr("k")).reply_rate_limit_per_minute == 30


async def test_the_31st_chip_reply_gets_429_and_publishes_no_event(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager, reply_limit=30) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["customer"]).room
        await post_turn(client, room)
        body = {"kind": "gate", "action": "ask"}
        statuses = [(await chip_reply(client, room, body)).status_code for _ in range(30)]
        assert statuses == [204] * 30
        queue = manager.subscribe(live, "customer")

        over = await chip_reply(client, room, body)

        assert over.status_code == 429
        assert queue.empty()


async def test_the_chip_reply_limit_is_per_participant(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager, reply_limit=2) as client:
        first, second = await make_room(client), await make_room(client)
        for room in (first, second):
            await post_turn(client, room)
        body = {"kind": "gate", "action": "ask"}
        for _ in range(2):
            await chip_reply(client, first, body)
        assert (await chip_reply(client, first, body)).status_code == 429
        assert (await chip_reply(client, second, body)).status_code == 204


async def test_the_reply_limit_is_separate_from_the_turn_limit(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager, turn_limit=1, reply_limit=3) as client:
        room = await make_room(client)
        assert (await post_turn(client, room)).status_code == 200
        body = {"kind": "gate", "action": "ask"}
        # Replies do not spend the turn budget, and the spent turn budget does not block replies.
        assert [(await chip_reply(client, room, body)).status_code for _ in range(3)] == [204] * 3
        assert (await chip_reply(client, room, body)).status_code == 429
        # An exhausted reply budget does not block turns beyond their own limit.
        assert (await post_turn(client, room)).status_code == 429
    assert gnani.stt_calls == 1


async def test_quick_replies_are_limited_too_and_share_the_budget_with_chip_replies(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager, reply_limit=3) as client:
        room = await make_room(client)
        live = manager.authorize(room["code"], room["customer"]).room
        await post_turn(client, room)
        phrase = {"phrase_id": "coming_2_min"}
        quick = [
            await client.post(
                f"/rooms/{room['code']}/quick-reply", json=phrase, headers=auth(room["rider"])
            )
            for _ in range(2)
        ]
        assert [r.status_code for r in quick] == [204, 204]
        assert (
            await chip_reply(client, room, {"kind": "gate", "action": "ask"})
        ).status_code == 204
        queue = manager.subscribe(live, "customer")

        over = await client.post(
            f"/rooms/{room['code']}/quick-reply", json=phrase, headers=auth(room["rider"])
        )

        assert over.status_code == 429
        assert queue.empty()
