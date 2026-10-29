from pathlib import Path

import httpx
import pytest

from saathi.rooms import RoomManager
from saathi.security_headers import content_security_policy
from test_demo import make_client, write_clips
from test_room_api import FakeGnani, auth, build_client, client, gnani, make_room, manager

__all__ = ["client", "gnani", "manager"]  # fixtures reused from test_room_api

PATHS = ["/", "/customer.html", "/rider.html", "/js/room-screen.js", "/languages", "/nope"]


def directives(policy: str) -> dict[str, str]:
    return dict(part.split(" ", 1) for part in policy.split("; "))


async def test_every_response_carries_the_policy(client: httpx.AsyncClient) -> None:
    expected = content_security_policy(allow_same_origin_frames=False)
    for path in PATHS:
        response = await client.get(path)
        assert response.headers["content-security-policy"] == expected, path


async def test_the_policy_has_no_inline_or_remote_allowance() -> None:
    policy = directives(content_security_policy(allow_same_origin_frames=False))
    assert policy["default-src"] == "'self'"
    assert policy["script-src"] == "'self'"
    assert policy["object-src"] == "'none'"
    assert policy["base-uri"] == "'none'"
    assert policy["frame-ancestors"] == "'none'"
    assert "unsafe-inline" not in " ".join(policy.values())
    assert "style-src" not in policy  # falls back to default-src 'self'


async def test_error_and_stream_responses_carry_the_policy(
    gnani: FakeGnani, manager: RoomManager
) -> None:
    async with build_client(gnani, manager) as client:
        room = await make_room(client)
        denied = await client.get(f"/rooms/{room['code']}/events", headers=auth("wrong"))
        closing = await client.delete(f"/rooms/{room['code']}", headers=auth(room["customer"]))
        assert closing.headers["content-security-policy"]
        assert denied.headers["content-security-policy"]


@pytest.mark.parametrize("framed", [False, True])
async def test_frame_ancestors_allows_same_origin_only_in_demo_mode(
    tmp_path: Path, framed: bool
) -> None:
    write_clips(tmp_path, [], [])
    async with make_client(RoomManager(max_rooms=3), tmp_path if framed else None) as client:
        header = (await client.get("/demo.html")).headers["content-security-policy"]
    assert directives(header)["frame-ancestors"] == ("'self'" if framed else "'none'")
