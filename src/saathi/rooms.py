"""In-memory rooms: a code, two role slots, random tokens, TTL expiry, events, short-lived audio.

Nothing here touches disk or logs. A room holds no transcripts. The only address data it keeps is
the delivery card (the latest value of each fact, in memory); that and turn audio are dropped when
the room closes or expires, and event payloads are not stored. State lives in one process, so
there is no locking: every method is synchronous and runs to completion on the event loop.
"""

import asyncio
import hmac
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from saathi.card import Card

Role = Literal["customer", "rider"]

# 31 symbols without I, L, O, 0 and 1, which look alike when read aloud or off a screen. Six of
# them carry about 29.7 bits, which is why joins are rate limited per IP.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
CODE_PATTERN = re.compile(rf"[{CODE_ALPHABET}]{{{CODE_LENGTH}}}")

IDLE_TTL_S = 30 * 60
HARD_TTL_S = 2 * 60 * 60
AUDIO_TTL_S = 60.0
MAX_AUDIO_PER_ROOM = 5
EVENT_QUEUE_SIZE = 32
TOKEN_BYTES = 16  # 128 bits


class RoomError(Exception):
    """Base class; the API maps each subclass to a generic response."""


class RoomAccessError(RoomError):
    """Unknown room, wrong or missing token, or expired room. Deliberately one error: telling
    them apart would let a stranger probe which codes exist."""


class RoomFullError(RoomError):
    """Both slots are taken."""


class RoomLimitError(RoomError):
    """Too many rooms alive at once."""


class SameLanguageError(RoomError):
    """Both people would speak the same language, so there is nothing to interpret."""


@dataclass(frozen=True)
class Event:
    name: str
    data: dict[str, Any]


@dataclass
class Participant:
    token: str
    language: str
    # The live SSE subscription, if any. A closed room puts None to end the stream.
    queue: asyncio.Queue[Event | None] | None = None


@dataclass
class StoredAudio:
    data: bytes
    expires_at: float


@dataclass
class Room:
    code: str
    created_at: float
    last_active: float
    participants: dict[Role, Participant] = field(default_factory=dict)
    audio: OrderedDict[str, StoredAudio] = field(default_factory=OrderedDict)
    card: Card = field(default_factory=Card)


@dataclass(frozen=True)
class Session:
    """An authenticated caller: the room and which slot their token opens."""

    room: Room
    role: Role


def other(role: Role) -> Role:
    return "rider" if role == "customer" else "customer"


class RoomManager:
    def __init__(
        self,
        max_rooms: int = 50,
        clock: Callable[[], float] = time.monotonic,
        idle_ttl_s: float = IDLE_TTL_S,
        hard_ttl_s: float = HARD_TTL_S,
        audio_ttl_s: float = AUDIO_TTL_S,
    ) -> None:
        self._max_rooms = max_rooms
        self._clock = clock
        self._idle_ttl_s = idle_ttl_s
        self._hard_ttl_s = hard_ttl_s
        self._audio_ttl_s = audio_ttl_s
        self._rooms: dict[str, Room] = {}

    # --- lifecycle ---------------------------------------------------------------------------

    def create(self, language: str) -> tuple[Room, str]:
        """Open a room; the creator is the customer. Returns the room and the customer's token."""
        self._purge()
        if len(self._rooms) >= self._max_rooms:
            raise RoomLimitError
        code = self._new_code()
        now = self._clock()
        token = _new_token()
        room = Room(code, now, now, {"customer": Participant(token, language)})
        self._rooms[code] = room
        return room, token

    def join(self, code: str, language: str) -> tuple[Room, str]:
        """Take the rider slot. The customer is told the rider arrived."""
        room = self._live(code)
        if room is None:
            raise RoomAccessError
        if "rider" in room.participants:
            raise RoomFullError
        if room.participants["customer"].language == language:
            raise SameLanguageError
        token = _new_token()
        room.participants["rider"] = Participant(token, language)
        self.touch(room)
        self.publish(room, "customer", Event("peer_joined", {"language": language}))
        return room, token

    def authorize(self, code: str, token: str) -> Session:
        """Resolve a code and token to a session, or raise RoomAccessError (fail closed)."""
        room = self._live(code)
        supplied = token.encode()
        matched: Role | None = None
        if room is not None:
            # Check both slots without stopping early so timing does not reveal which matched.
            for role, participant in room.participants.items():
                if hmac.compare_digest(participant.token.encode(), supplied):
                    matched = role
        if room is None or matched is None:
            raise RoomAccessError
        return Session(room, matched)

    def touch(self, room: Room) -> None:
        room.last_active = self._clock()

    def close(self, room: Room) -> None:
        """Remove the room and end every open event stream."""
        self._rooms.pop(room.code, None)
        room.audio.clear()
        room.card.clear()
        for participant in room.participants.values():
            if participant.queue is not None:
                _offer(participant.queue, None)
                participant.queue = None

    def is_live(self, room: Room) -> bool:
        return self._live(room.code) is room

    # --- events ------------------------------------------------------------------------------

    def subscribe(self, room: Room, role: Role) -> asyncio.Queue[Event | None]:
        """Start receiving events for a role. A newer connection replaces an older one, which
        is what a phone that reconnects after a network change needs."""
        participant = room.participants[role]
        if participant.queue is not None:
            _offer(participant.queue, None)
        queue: asyncio.Queue[Event | None] = asyncio.Queue(EVENT_QUEUE_SIZE)
        participant.queue = queue
        return queue

    def unsubscribe(self, room: Room, role: Role, queue: asyncio.Queue[Event | None]) -> None:
        participant = room.participants[role]
        if participant.queue is queue:
            participant.queue = None

    def is_subscribed(self, room: Room, role: Role) -> bool:
        participant = room.participants.get(role)
        return participant is not None and participant.queue is not None

    def publish(self, room: Room, role: Role, event: Event) -> None:
        """Deliver to a role's stream; dropped if nobody is listening (the state snapshot sent on
        connect covers presence, and turns are not replayed)."""
        participant = room.participants.get(role)
        if participant is not None and participant.queue is not None:
            _offer(participant.queue, event)

    def snapshot(self, room: Room, role: Role) -> Event:
        peer = room.participants.get(other(role))
        return Event(
            "state",
            {
                "role": role,
                "language": room.participants[role].language,
                "peer_joined": peer is not None,
                "peer_language": peer.language if peer else None,
            },
        )

    # --- turn audio --------------------------------------------------------------------------

    def store_audio(self, room: Room, data: bytes) -> str:
        now = self._clock()
        self._drop_expired_audio(room, now)
        audio_id = secrets.token_urlsafe(TOKEN_BYTES)
        room.audio[audio_id] = StoredAudio(data, now + self._audio_ttl_s)
        while len(room.audio) > MAX_AUDIO_PER_ROOM:
            room.audio.popitem(last=False)
        return audio_id

    def get_audio(self, room: Room, audio_id: str) -> bytes | None:
        self._drop_expired_audio(room, self._clock())
        stored = room.audio.get(audio_id)
        return stored.data if stored else None

    # --- internals ---------------------------------------------------------------------------

    def _live(self, code: str) -> Room | None:
        room = self._rooms.get(code)
        if room is None:
            return None
        if self._expired(room, self._clock()):
            self.close(room)
            return None
        return room

    def _expired(self, room: Room, now: float) -> bool:
        return (
            now - room.last_active >= self._idle_ttl_s or now - room.created_at >= self._hard_ttl_s
        )

    def _purge(self) -> None:
        now = self._clock()
        for room in [r for r in self._rooms.values() if self._expired(r, now)]:
            self.close(room)

    def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self._rooms:
                return code

    @staticmethod
    def _drop_expired_audio(room: Room, now: float) -> None:
        for audio_id in [i for i, a in room.audio.items() if a.expires_at <= now]:
            del room.audio[audio_id]


def _new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def _offer(queue: asyncio.Queue[Event | None], item: Event | None) -> None:
    """Put without blocking. A full queue means a stalled reader: drop its oldest event so a slow
    phone can never grow memory or block the sender."""
    if queue.full():
        queue.get_nowait()
    queue.put_nowait(item)
