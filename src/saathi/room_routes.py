"""HTTP endpoints for rooms. Every route after create/join needs `Authorization: Bearer <token>`.

Failures are generic on purpose: an unknown room, a wrong token, a token from another room and an
expired room all give the same 404, so a stranger cannot learn which codes exist. Transcripts and
translations are never logged; log lines carry language codes, timings and counts only.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Path, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from saathi.audio import MAX_AUDIO_BYTES, AudioError, AudioTooLargeError, wav_duration_s
from saathi.card import ChipAction
from saathi.facts import Fact, FactKind
from saathi.gnani import GnaniClient, GnaniError
from saathi.labels import chip_label
from saathi.languages import LANGUAGES
from saathi.pipeline import (
    NoSpeechError,
    TranslationUnavailableError,
    UnreliableTranslationError,
    run_turn,
)
from saathi.quickreplies import IDS_BY_ROLE, QuickReplyId, ReviewStatus, phrase_for
from saathi.ratelimit import SlidingWindowLimiter
from saathi.repeatprompts import RepeatReason, repeat_prompt, repeat_reason
from saathi.rooms import (
    CODE_ALPHABET,
    CODE_LENGTH,
    Event,
    Role,
    Room,
    RoomAccessError,
    RoomFullError,
    RoomLimitError,
    RoomManager,
    SameLanguageError,
    Session,
    other,
)
from saathi.translate import Translator
from saathi.unavailable import translation_unavailable_text, unavailable_text

log = logging.getLogger(__name__)

KEEPALIVE_S = 15.0  # SSE comment interval; keeps proxies and phones from dropping an idle stream
WAV_CONTENT_TYPES = frozenset({"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"})
MAX_TOKEN_CHARS = 64  # real tokens are 22 characters; anything longer is not one

CodePath = Annotated[str, Path(pattern=rf"^[{CODE_ALPHABET}]{{{CODE_LENGTH}}}$")]
AudioIdPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{16,64}$")]


class LanguageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(max_length=8)

    @field_validator("language")
    @classmethod
    def _known_language(cls, value: str) -> str:
        if value not in LANGUAGES:
            raise ValueError("unsupported language")
        return value


class QuickReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phrase_id: QuickReplyId


class ChipReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: FactKind
    action: ChipAction


class RoomOut(BaseModel):
    code: str
    token: str
    role: Role
    language: str
    peer_language: str | None = None


class FactOut(BaseModel):
    kind: str
    value: str
    heard: str
    confidence: str
    ambiguous: bool
    reading: str | None
    local: str | None  # a landmark in the listener's language; None when no plausible rendering
    label: str  # the class name (gate, floor, ...) in the language of whoever reads the chip
    label_status: str  # source, reviewed or pending (unreviewed spelling)


class TimingsOut(BaseModel):
    """Server-side stage durations of one turn; numbers only, no content."""

    stt_ms: float
    translate_ms: float
    tts_ms: float
    total_ms: float


class RepeatOut(BaseModel):
    """Asks the speaker to say it again, in their own language. Never blocks the turn."""

    reason: RepeatReason
    text: str
    review_status: ReviewStatus


class TurnOut(BaseModel):
    turn_id: str
    facts: list[FactOut]
    verified: bool
    repeat: RepeatOut | None = None
    timings: TimingsOut  # shown to the speaker only; the listener's event does not carry it


def _fact_out(fact: Fact, language: str) -> FactOut:
    # Spans are offsets into a transcript the client never receives, so they are left out.
    label = chip_label(fact.kind, language)
    return FactOut(
        label=label.text,
        label_status=label.status,
        kind=fact.kind,
        value=fact.value,
        heard=fact.heard,
        confidence=fact.confidence,
        ambiguous=fact.ambiguous,
        reading=fact.reading,
        local=fact.local,
    )


class CardEntryOut(BaseModel):
    fact: FactOut
    previous: str | None  # the value this one replaced; set until the listener confirms it
    previous_local: str | None  # that old value as a landmark in the listener's language, if any
    confirmed: bool
    question: str | None  # the listener's question about this value, in the viewer's language


def _card_out(room: Room, language: str) -> list[dict[str, Any]]:
    """The room's delivery card as one viewer reads it. Content is never logged."""
    return [
        CardEntryOut(
            fact=_fact_out(entry.fact, language),
            previous=entry.previous,
            previous_local=entry.previous_local,
            confirmed=entry.confirmed,
            question=f"{chip_label(entry.fact.kind, language).text}?" if entry.asked else None,
        ).model_dump()
        for entry in room.card.entries.values()
    ]


def _card_event(room: Room, language: str) -> Event:
    return Event("card", {"entries": _card_out(room, language)})


def _repeat_out(verified: bool, fact_count: int, speaker: Role, language: str) -> RepeatOut | None:
    reason = repeat_reason(verified, fact_count, speaker)
    prompt = repeat_prompt(language, reason) if reason else None
    if reason is None or prompt is None:
        return None
    return RepeatOut(reason=reason, text=prompt.text, review_status=prompt.review_status)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _sse(event: Event) -> str:
    return f"event: {event.name}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


def room_router(
    manager: RoomManager,
    gnani: GnaniClient,
    translator: Translator,
    room_limit_per_minute: int,
    turn_limit_per_minute: int,
    reply_limit_per_minute: int,
    demo_input: bool = False,
) -> APIRouter:
    router = APIRouter()
    create_limiter = SlidingWindowLimiter(room_limit_per_minute)
    join_limiter = SlidingWindowLimiter(room_limit_per_minute)
    turn_limiter = SlidingWindowLimiter(turn_limit_per_minute)
    reply_limiter = SlidingWindowLimiter(reply_limit_per_minute)
    phrase_audio: dict[tuple[str, str], bytes] = {}

    def authenticate(
        code: CodePath, authorization: Annotated[str | None, Header()] = None
    ) -> Session:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token or len(token) > MAX_TOKEN_CHARS:
            raise HTTPException(404, "room not found")
        try:
            return manager.authorize(code, token)
        except RoomAccessError as exc:
            raise HTTPException(404, "room not found") from exc

    Authed = Annotated[Session, Depends(authenticate)]

    def check_reply_limit(session: Session) -> None:
        """Quick replies and chip replies share one budget per participant."""
        if not reply_limiter.allow(f"{session.room.code}:{session.role}"):
            raise HTTPException(429, "too many requests")

    @router.post("/rooms", status_code=201)
    async def create_room(body: LanguageIn, request: Request) -> RoomOut:
        if not create_limiter.allow(_client_ip(request)):
            raise HTTPException(429, "too many requests")
        try:
            room, token = manager.create(body.language)
        except RoomLimitError as exc:
            raise HTTPException(503, "service busy, retry shortly") from exc
        return RoomOut(code=room.code, token=token, role="customer", language=body.language)

    @router.post("/rooms/{code}/join")
    async def join_room(code: CodePath, body: LanguageIn, request: Request) -> RoomOut:
        # Counted before the lookup, so guessing codes is limited whether or not a guess hits.
        if not join_limiter.allow(_client_ip(request)):
            raise HTTPException(429, "too many requests")
        try:
            room, token = manager.join(code, body.language)
        except RoomAccessError as exc:
            raise HTTPException(404, "room not found") from exc
        except RoomFullError as exc:
            raise HTTPException(409, "room is full") from exc
        except SameLanguageError as exc:
            raise HTTPException(400, "unsupported language pair") from exc
        return RoomOut(
            code=room.code,
            token=token,
            role="rider",
            language=body.language,
            peer_language=room.participants["customer"].language,
        )

    @router.delete("/rooms/{code}", status_code=204)
    async def close_room(session: Authed) -> None:
        manager.close(session.room)

    @router.get("/rooms/{code}/events")
    async def events(session: Authed) -> StreamingResponse:
        room, role = session.room, session.role
        queue = manager.subscribe(room, role)  # before returning, so no event falls in a gap

        async def stream() -> AsyncIterator[str]:
            try:
                state = manager.snapshot(room, role)
                card = _card_out(room, room.participants[role].language)
                yield _sse(Event(state.name, {**state.data, "card": card}))
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), KEEPALIVE_S)
                    except TimeoutError:
                        if not manager.is_live(room):
                            break
                        yield ": keepalive\n\n"
                        continue
                    if item is None:
                        yield _sse(Event("closed", {}))
                        break
                    yield _sse(item)
            finally:
                manager.unsubscribe(room, role, queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.post("/rooms/{code}/turn")
    async def turn(
        session: Authed,
        request: Request,
        audio: Annotated[UploadFile, File()],
        x_demo_clip: Annotated[str | None, Header()] = None,
    ) -> TurnOut:
        # Either person may speak: they translate from their own language into the other's.
        room, speaker, listener = session.room, session.role, other(session.role)
        peer = room.participants.get(listener)
        if peer is None:
            raise HTTPException(409, f"waiting for the {listener} to join")
        if not turn_limiter.allow(_client_ip(request)):
            raise HTTPException(429, "too many requests")

        # Everything up to run_turn is free; reject bad input before any paid call.
        data = await _read_wav(audio)
        src, tgt = room.participants[speaker].language, peer.language
        try:
            result = await run_turn(data, src, tgt, gnani, translator)
        except NoSpeechError as exc:
            raise HTTPException(
                422, {"code": "no_speech", "message": "no speech detected"}
            ) from exc
        except UnreliableTranslationError as exc:
            raise HTTPException(
                422, {"code": "unreliable_translation", "message": "could not translate reliably"}
            ) from exc
        except GnaniError as exc:
            if exc.status == 429:
                raise HTTPException(503, "speech service busy, retry shortly") from exc
            raise HTTPException(
                502, {"code": "speech_unavailable", "message": unavailable_text(src)}
            ) from exc
        except TranslationUnavailableError as exc:
            raise HTTPException(
                502,
                {"code": "translation_unavailable", "message": translation_unavailable_text(src)},
            ) from exc

        if not manager.is_live(room):  # closed or expired while the paid calls ran
            raise HTTPException(404, "room not found")
        manager.touch(room)
        turn_id = manager.store_audio(room, result.audio)
        # Each side reads the labels in its own language; the facts themselves are the same.
        facts = [_fact_out(fact, src) for fact in result.facts]
        heard_facts = [_fact_out(fact, tgt) for fact in result.facts]
        manager.publish(
            room,
            listener,
            Event(
                "turn",
                {
                    "turn_id": turn_id,
                    "src": src,
                    "tgt": tgt,
                    "translation": result.translation,
                    "facts": [fact.model_dump() for fact in heard_facts],
                    "verified": result.verified,
                    # Lets the listener's screen say this was a prepared clip, not live speech.
                    "demo_clip": demo_input and x_demo_clip == "1",
                    "audio_path": f"/rooms/{room.code}/turns/{turn_id}/audio",
                },
            ),
        )
        if speaker == "customer":  # a rider's facts show for that turn only, never on the card
            room.card.update(result.facts)
            if result.facts:
                for role in (speaker, listener):
                    manager.publish(room, role, _card_event(room, room.participants[role].language))
        timings = result.timings
        log.info(
            "room turn %s->%s facts=%d stt=%.0fms translate=%.0fms tts=%.0fms total=%.0fms",
            src,
            tgt,
            len(facts),
            timings.stt_ms,
            timings.translate_ms,
            timings.tts_ms,
            timings.total_ms,
        )
        return TurnOut(
            turn_id=turn_id,
            facts=facts,
            verified=result.verified,
            repeat=_repeat_out(result.verified, len(facts), speaker, src),
            timings=TimingsOut(**vars(timings)),
        )

    @router.get("/rooms/{code}/turns/{turn_id}/audio")
    async def turn_audio(session: Authed, turn_id: AudioIdPath) -> Response:
        data = manager.get_audio(session.room, turn_id)
        if data is None:
            raise HTTPException(404, "audio not found")
        return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @router.post("/rooms/{code}/quick-reply", status_code=204)
    async def quick_reply(session: Authed, body: QuickReplyIn) -> None:
        check_reply_limit(session)
        if body.phrase_id not in IDS_BY_ROLE[session.role]:
            raise HTTPException(422, "phrase not available to this role")
        room, recipient = session.room, other(session.role)
        peer = room.participants.get(recipient)
        if peer is None:
            raise HTTPException(409, f"waiting for the {recipient} to join")
        # The phrase is spoken to the recipient, so it is looked up in their language.
        phrase = phrase_for(peer.language, body.phrase_id)
        if phrase is None:  # no text for this language: refuse, never guess
            raise HTTPException(400, "quick replies are not available in this language")
        manager.touch(room)
        data: dict[str, Any] = {
            "phrase_id": body.phrase_id,
            "text": phrase.text,
            "review_status": phrase.review_status,
            "audio_path": None,
        }
        key = (peer.language, body.phrase_id)
        try:
            if key not in phrase_audio:  # fixed phrases hold no personal data, so cache them
                voice = LANGUAGES[peer.language]
                phrase_audio[key] = await gnani.synthesize(
                    phrase.text, voice.gnani_code, voice.tts_voice
                )
            audio_id = manager.store_audio(room, phrase_audio[key])
            data["audio_path"] = f"/rooms/{room.code}/turns/{audio_id}/audio"
        except GnaniError:
            log.warning("quick reply audio unavailable lang=%s", peer.language)  # text still sent
        manager.publish(room, recipient, Event("quick_reply", data))

    @router.post("/rooms/{code}/chip-reply", status_code=204)
    async def chip_reply(session: Authed, body: ChipReplyIn) -> None:
        check_reply_limit(session)
        # The card is built from the customer's turns, so the rider is the one who answers it.
        if session.role != "rider":
            raise HTTPException(403, "only the rider can answer the card")
        room = session.room
        if not room.card.respond(body.kind, body.action):
            raise HTTPException(422, "that detail is not on the card")
        manager.touch(room)
        for role in room.participants:
            manager.publish(room, role, _card_event(room, room.participants[role].language))

    return router


async def _read_wav(upload: UploadFile) -> bytes:
    """Read and validate an uploaded WAV. Raises HTTPException with a generic message."""
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in WAV_CONTENT_TYPES:
        raise HTTPException(415, "audio must be a WAV file")
    data = await upload.read(MAX_AUDIO_BYTES + 1)
    try:
        wav_duration_s(data)
    except AudioTooLargeError as exc:
        raise HTTPException(413, "audio file too large") from exc
    except AudioError as exc:
        raise HTTPException(400, "audio must be a valid WAV under 60 seconds") from exc
    return data
