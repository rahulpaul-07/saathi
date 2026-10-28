import re

import pytest

from saathi.rooms import (
    CODE_ALPHABET,
    CODE_PATTERN,
    MAX_AUDIO_PER_ROOM,
    Event,
    RoomAccessError,
    RoomFullError,
    RoomLimitError,
    RoomManager,
    SameLanguageError,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def manager(clock: Clock) -> RoomManager:
    return RoomManager(max_rooms=3, clock=clock, idle_ttl_s=100, hard_ttl_s=300, audio_ttl_s=10)


def test_create_and_join_issue_distinct_128_bit_tokens(manager: RoomManager) -> None:
    room, customer_token = manager.create("en")
    _, rider_token = manager.join(room.code, "kn")

    assert CODE_PATTERN.fullmatch(room.code)
    assert customer_token != rider_token
    for token in (customer_token, rider_token):
        assert re.fullmatch(r"[A-Za-z0-9_-]{22}", token)  # 16 bytes, url-safe base64
    assert manager.authorize(room.code, customer_token).role == "customer"
    assert manager.authorize(room.code, rider_token).role == "rider"


def test_codes_use_the_unambiguous_alphabet() -> None:
    assert not set("ILO01") & set(CODE_ALPHABET)
    assert len(CODE_ALPHABET) == 31


def test_third_participant_is_refused(manager: RoomManager) -> None:
    room, _ = manager.create("en")
    manager.join(room.code, "kn")
    with pytest.raises(RoomFullError):
        manager.join(room.code, "hi")


def test_same_language_join_is_refused_and_leaves_the_slot_free(manager: RoomManager) -> None:
    room, _ = manager.create("en")
    with pytest.raises(SameLanguageError):
        manager.join(room.code, "en")
    manager.join(room.code, "kn")


def test_join_unknown_room_fails(manager: RoomManager) -> None:
    with pytest.raises(RoomAccessError):
        manager.join("ABCDEF", "kn")


def test_token_from_another_room_is_rejected(manager: RoomManager) -> None:
    room_a, token_a = manager.create("en")
    room_b, _ = manager.create("en")
    assert manager.authorize(room_a.code, token_a).room is room_a
    with pytest.raises(RoomAccessError):
        manager.authorize(room_b.code, token_a)


@pytest.mark.parametrize("token", ["", "x", "é" * 22])
def test_bad_tokens_are_rejected(manager: RoomManager, token: str) -> None:
    room, _ = manager.create("en")
    with pytest.raises(RoomAccessError):
        manager.authorize(room.code, token)


def test_room_expires_when_idle_and_activity_extends_it(manager: RoomManager, clock: Clock) -> None:
    room, token = manager.create("en")
    clock.now += 99
    manager.touch(room)
    clock.now += 99
    assert manager.authorize(room.code, token).room is room  # touched, so still alive
    clock.now += 100
    with pytest.raises(RoomAccessError):
        manager.authorize(room.code, token)


def test_room_expires_at_the_hard_limit_even_when_busy(manager: RoomManager, clock: Clock) -> None:
    room, token = manager.create("en")
    for _ in range(4):
        clock.now += 80
        manager.touch(room)
    with pytest.raises(RoomAccessError):
        manager.authorize(room.code, token)


def test_expired_rooms_do_not_count_toward_the_room_cap(manager: RoomManager, clock: Clock) -> None:
    for _ in range(3):
        manager.create("en")
    with pytest.raises(RoomLimitError):
        manager.create("en")
    clock.now += 101
    manager.create("en")


async def test_events_reach_only_the_addressed_role(manager: RoomManager) -> None:
    room, _ = manager.create("en")
    manager.join(room.code, "kn")
    rider_queue = manager.subscribe(room, "rider")
    customer_queue = manager.subscribe(room, "customer")

    manager.publish(room, "rider", Event("turn", {"n": 1}))

    assert rider_queue.get_nowait() == Event("turn", {"n": 1})
    assert customer_queue.empty()


async def test_newer_subscription_replaces_the_older_one(manager: RoomManager) -> None:
    room, _ = manager.create("en")
    first = manager.subscribe(room, "customer")
    second = manager.subscribe(room, "customer")

    manager.publish(room, "customer", Event("x", {}))

    assert first.get_nowait() is None  # told to end
    assert second.get_nowait() == Event("x", {})


async def test_full_queue_drops_oldest_instead_of_blocking(manager: RoomManager) -> None:
    room, _ = manager.create("en")
    queue = manager.subscribe(room, "customer")
    for n in range(queue.maxsize + 5):
        manager.publish(room, "customer", Event("x", {"n": n}))
    first = queue.get_nowait()
    assert first is not None and first.data["n"] == 5


async def test_close_ends_streams_and_forgets_the_room(manager: RoomManager) -> None:
    room, token = manager.create("en")
    queue = manager.subscribe(room, "customer")
    manager.close(room)
    assert queue.get_nowait() is None
    with pytest.raises(RoomAccessError):
        manager.authorize(room.code, token)


def test_turn_audio_expires_and_is_capped(manager: RoomManager, clock: Clock) -> None:
    room, _ = manager.create("en")
    audio_id = manager.store_audio(room, b"wav")
    assert manager.get_audio(room, audio_id) == b"wav"
    clock.now += 10
    assert manager.get_audio(room, audio_id) is None

    ids = [manager.store_audio(room, b"x") for _ in range(MAX_AUDIO_PER_ROOM + 2)]
    assert manager.get_audio(room, ids[0]) is None
    assert manager.get_audio(room, ids[-1]) == b"x"


def test_snapshot_reports_peer_presence(manager: RoomManager) -> None:
    room, _ = manager.create("en")
    assert manager.snapshot(room, "customer").data["peer_joined"] is False
    manager.join(room.code, "kn")
    assert manager.snapshot(room, "customer").data["peer_language"] == "kn"
    assert manager.snapshot(room, "rider").data["peer_language"] == "en"
