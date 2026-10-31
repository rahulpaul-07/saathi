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


class Sleeps:
    """Stands in for asyncio.sleep so the retry wait costs no time."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


@pytest.fixture
def sleeps() -> Sleeps:
    return Sleeps()


@pytest.fixture
def retrying(sleeps: Sleeps) -> GnaniClient:
    settings = Settings(gnani_api_key=SecretStr("k"), gnani_base_url=BASE)
    return GnaniClient(settings, sleep=sleeps, retry_wait_s=0.5)


@respx.mock
async def test_stt_retries_once_after_a_5xx_and_succeeds(
    retrying: GnaniClient, sleeps: Sleeps
) -> None:
    route = respx.post(f"{BASE}{STT_PATH}").mock(
        side_effect=[
            httpx.Response(504, text="gateway timeout"),
            httpx.Response(200, json={"success": True, "transcript": "namaskar"}),
        ]
    )
    assert await retrying.transcribe(b"x", "a.wav", "bn-IN") == "namaskar"
    assert route.call_count == 2
    assert sleeps.waits == [0.5]


@respx.mock
async def test_tts_retries_once_after_a_timeout_and_succeeds(
    retrying: GnaniClient, sleeps: Sleeps
) -> None:
    route = respx.post(f"{BASE}{TTS_PATH}").mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, content=make_streaming_wav())]
    )
    assert wav_duration_s(await retrying.synthesize("hi", "kn-IN", "Saanvi")) == pytest.approx(0.5)
    assert route.call_count == 2
    assert sleeps.waits == [0.5]


@respx.mock
async def test_a_second_failure_is_final_and_keeps_the_upstream_status(
    retrying: GnaniClient,
) -> None:
    route = respx.post(f"{BASE}{STT_PATH}").mock(return_value=httpx.Response(504, text="x"))
    with pytest.raises(GnaniError) as info:
        await retrying.transcribe(b"x", "a.wav", "bn-IN")
    assert route.call_count == 2  # one retry, no more
    assert info.value.status == 504


@respx.mock
@pytest.mark.parametrize(
    "failure", [httpx.Response(429), httpx.Response(400), httpx.ConnectError("x")]
)
async def test_rate_limits_client_errors_and_connect_errors_are_not_retried(
    retrying: GnaniClient, sleeps: Sleeps, failure: httpx.Response | Exception
) -> None:
    route = respx.post(f"{BASE}{STT_PATH}").mock(side_effect=[failure])
    with pytest.raises(GnaniError):
        await retrying.transcribe(b"x", "a.wav", "bn-IN")
    assert route.call_count == 1
    assert sleeps.waits == []


@respx.mock
async def test_failures_log_the_status_but_never_the_response_body(
    retrying: GnaniClient, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post(f"{BASE}{STT_PATH}").mock(return_value=httpx.Response(504, text="PRIVATE-BODY"))
    with pytest.raises(GnaniError):
        await retrying.transcribe(b"x", "a.wav", "bn-IN")
    assert "504" in caplog.text
    assert "PRIVATE-BODY" not in caplog.text


@respx.mock
async def test_the_api_key_is_not_in_the_settings_repr_or_in_failure_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    key = "key-that-must-not-leak"
    settings = Settings(gnani_api_key=SecretStr(key), gnani_base_url=BASE)
    respx.post(f"{BASE}{STT_PATH}").mock(return_value=httpx.Response(500, text="x"))
    gnani = GnaniClient(settings, retry_wait_s=0)
    with caplog.at_level("DEBUG"), pytest.raises(GnaniError):
        await gnani.transcribe(b"x", "a.wav", "bn-IN")
    assert key not in repr(settings) and key not in str(settings)
    assert key not in caplog.text
