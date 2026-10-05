import httpx
import pytest
import respx
from pydantic import SecretStr

from saathi.audio import wav_duration_s
from saathi.config import Settings
from saathi.gnani import STT_PATH, TTS_PATH, GnaniClient, GnaniError
from wavs import make_streaming_wav

BASE = "https://api.test"


@pytest.fixture
def client() -> GnaniClient:
    settings = Settings(gnani_api_key=SecretStr("k"), gnani_base_url=BASE)
    return GnaniClient(settings)


@respx.mock
async def test_transcribe_sends_key_language_and_returns_transcript(client: GnaniClient) -> None:
    route = respx.post(f"{BASE}{STT_PATH}").mock(
        return_value=httpx.Response(200, json={"success": True, "transcript": "namaskar"})
    )
    assert await client.transcribe(b"RIFF", "a.wav", "bn-IN") == "namaskar"
    request = route.calls.last.request
    assert request.headers["X-API-Key-ID"] == "k"
    assert b'name="language_code"' in request.content and b"bn-IN" in request.content


@respx.mock
async def test_synthesize_returns_audio_bytes(client: GnaniClient) -> None:
    route = respx.post(f"{BASE}{TTS_PATH}").mock(
        return_value=httpx.Response(200, content=make_streaming_wav())
    )
    audio = await client.synthesize("hi", "kn-IN", "Saanvi")
    # Gnani sends 0xFFFFFFFF sizes; the client must hand back a WAV with real ones.
    assert wav_duration_s(audio) == pytest.approx(0.5)
    assert b'"timbre-v2.5"' in route.calls.last.request.content


@respx.mock
async def test_synthesize_rejects_non_wav_payload(client: GnaniClient) -> None:
    respx.post(f"{BASE}{TTS_PATH}").mock(return_value=httpx.Response(200, content=b"<html>"))
    with pytest.raises(GnaniError):
        await client.synthesize("hi", "kn-IN", "Saanvi")


@respx.mock
async def test_upstream_error_becomes_generic_gnani_error(client: GnaniClient) -> None:
    respx.post(f"{BASE}{STT_PATH}").mock(return_value=httpx.Response(429, text="secret detail"))
    with pytest.raises(GnaniError) as info:
        await client.transcribe(b"x", "a.wav", "bn-IN")
    assert info.value.status == 429
    assert "secret detail" not in str(info.value)


@respx.mock
async def test_transport_failure_becomes_gnani_error(client: GnaniClient) -> None:
    respx.post(f"{BASE}{TTS_PATH}").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(GnaniError):
        await client.synthesize("hi", "kn-IN", "Saanvi")
