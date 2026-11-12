import httpx

from test_room_api import client, gnani, manager

__all__ = ["client", "gnani", "manager"]  # fixtures reused from test_room_api

# Pages, scripts and styles are not fingerprinted, so after a deploy a browser must ask again.
ASSETS = ["/", "/index.html", "/app.css", "/js/landing.js", "/favicon.svg"]


async def test_pages_and_assets_are_revalidated_on_every_load(client: httpx.AsyncClient) -> None:
    for path in ASSETS:
        response = await client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "no-cache", path


async def test_an_unchanged_file_is_answered_with_an_empty_304(client: httpx.AsyncClient) -> None:
    first = await client.get("/app.css")
    again = await client.get("/app.css", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["cache-control"] == "no-cache"


async def test_a_changed_file_is_sent_in_full(client: httpx.AsyncClient) -> None:
    stale = await client.get("/app.css", headers={"If-None-Match": '"not-the-current-version"'})
    assert stale.status_code == 200
    assert stale.content


async def test_api_responses_are_not_given_a_cache_policy(client: httpx.AsyncClient) -> None:
    response = await client.get("/languages")
    assert response.status_code == 200
    assert "cache-control" not in response.headers
