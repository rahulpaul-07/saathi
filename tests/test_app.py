import base64
import json
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import respx
from pydantic import SecretStr

from saathi.app import create_app
from saathi.audio import MAX_AUDIO_BYTES, wav_duration_s
from saathi.config import Settings
from saathi.gnani import STT_PATH, TTS_PATH, GnaniClient
from wavs import make_streaming_wav, make_wav

BASE = "https://api.test"


class FakeTranslator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.output = "kannada text"

    def translate(self, text: str, src: str, tgt: str) -> str:
        self.calls.append((text, src, tgt))
        return self.output


@pytest.fixture
def translator() -> FakeTranslator:
    return FakeTranslator()


def build_client(translator: FakeTranslator, rate_limit: int = 100) -> httpx.AsyncClient:
    settings = Settings(
        gnani_api_key=SecretStr("k"), gnani_base_url=BASE, turn_rate_limit_per_minute=rate_limit
    )
    app = create_app(settings, GnaniClient(settings), translator)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://saathi")


@pytest.fixture
async def client(translator: FakeTranslator) -> AsyncIterator[httpx.AsyncClient]:
    async with build_client(translator) as c:
        yield c


@pytest.fixture
def upstream() -> Iterator[respx.MockRouter]:
    def stt(request: httpx.Request) -> httpx.Response:
        # Like the real service: audio that is not a WAV gets a 400, never a transcript.
        if b"RIFF" not in request.content or b"WAVE" not in request.content:
            return httpx.Response(400, text="bad audio")
        return httpx.Response(200, json={"success": True, "transcript": "namaskar"})

    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE}{STT_PATH}").mock(side_effect=stt)
        router.post(f"{BASE}{TTS_PATH}").mock(
            return_value=httpx.Response(200, content=make_streaming_wav())
        )
        yield router


async def post_turn(
    client: httpx.AsyncClient, audio: bytes, src: str = "bn", tgt: str = "kn"
) -> httpx.Response:
    return await client.post(
        "/turn", files={"audio": ("a.wav", audio, "audio/wav")}, data={"src": src, "tgt": tgt}
    )


async def test_turn_runs_all_three_stages_and_reports_timings(
    client: httpx.AsyncClient, translator: FakeTranslator, upstream: respx.MockRouter
) -> None:
    response = await post_turn(client, make_wav())

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "namaskar"
    assert body["translation"] == "kannada text"
    assert wav_duration_s(base64.b64decode(body["audio_base64"])) == pytest.approx(0.5)
    timings = body["timings"]
    assert set(timings) == {"stt_ms", "translate_ms", "tts_ms", "total_ms"}
    stages = timings["stt_ms"] + timings["translate_ms"] + timings["tts_ms"]
    assert timings["total_ms"] == pytest.approx(stages, abs=1.0)

    assert translator.calls == [("namaskar", "bn", "kn")]
    stt_request = upstream.calls[0].request
    assert b"bn-IN" in stt_request.content
    tts_payload = json.loads(upstream.calls[1].request.content)
    assert (tts_payload["text"], tts_payload["language"], tts_payload["voice"]) == (
        "kannada text",
        "kn-IN",
        "Saanvi",
    )


async def test_reverse_direction_uses_target_language_voice(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    response = await post_turn(client, make_wav(), src="ta", tgt="hi")
    assert response.status_code == 200
    assert json.loads(upstream.calls[1].request.content)["voice"] == "Nalini"


@pytest.mark.parametrize(("src", "tgt"), [("bn", "ur"), ("bn", "bn"), ("xx", "kn"), ("bn", "")])
async def test_unsupported_pair_is_rejected_before_any_paid_call(
    client: httpx.AsyncClient, upstream: respx.MockRouter, src: str, tgt: str
) -> None:
    response = await post_turn(client, make_wav(), src=src, tgt=tgt)
    assert response.status_code in (400, 422)
    assert upstream.calls.call_count == 0


@pytest.mark.parametrize(
    ("audio", "status"),
    [
        (b"not a wav file", 400),
        (make_wav(61, rate=8000), 400),  # longer than Prisma's 60 s limit
        (b"RIFF" + b"\x00" * MAX_AUDIO_BYTES, 413),
    ],
    ids=["not-wav", "too-long", "too-large"],
)
async def test_bad_audio_is_rejected_before_any_paid_call(
    client: httpx.AsyncClient, upstream: respx.MockRouter, audio: bytes, status: int
) -> None:
    response = await post_turn(client, audio)
    assert response.status_code == status
    assert upstream.calls.call_count == 0


async def test_missing_audio_field_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/turn", data={"src": "bn", "tgt": "kn"})
    assert response.status_code == 422


async def test_empty_transcript_returns_422_and_skips_translate_and_tts(
    client: httpx.AsyncClient, translator: FakeTranslator, upstream: respx.MockRouter
) -> None:
    upstream.post(f"{BASE}{STT_PATH}").mock(
        return_value=httpx.Response(200, json={"success": True, "transcript": "  "})
    )
    response = await post_turn(client, make_wav())
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "no_speech", "message": "no speech detected"}
    assert translator.calls == []
    assert upstream.calls.call_count == 1


async def test_degenerate_translation_returns_422_with_transcript_and_skips_tts(
    translator: FakeTranslator, upstream: respx.MockRouter
) -> None:
    translator.output = "ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ"
    async with build_client(translator) as client:
        response = await post_turn(client, make_wav())
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "unreliable_translation"
    assert detail["transcript"] == "namaskar"
    assert detail["message"]
    assert upstream.calls.call_count == 1  # STT only, no paid TTS


async def test_upstream_failure_returns_generic_502(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post(f"{BASE}{STT_PATH}").mock(
        return_value=httpx.Response(500, text="internal secret detail")
    )
    response = await post_turn(client, make_wav())
    assert response.status_code == 502
    assert "secret" not in response.text


async def test_upstream_400_asks_for_a_new_recording_and_is_not_retried(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    route = upstream.post(f"{BASE}{STT_PATH}").mock(
        return_value=httpx.Response(400, text="secret upstream body")
    )
    response = await post_turn(client, make_wav())
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "bad_recording"
    assert "secret" not in response.text
    assert route.call_count == 1


async def test_upstream_rate_limit_is_reported_as_retryable_503(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post(f"{BASE}{STT_PATH}").mock(return_value=httpx.Response(429, text="slow down"))
    response = await post_turn(client, make_wav())
    assert response.status_code == 503
    assert "retry" in response.json()["detail"]


async def test_rate_limit_returns_429_after_the_cap(
    translator: FakeTranslator, upstream: respx.MockRouter
) -> None:
    async with build_client(translator, rate_limit=2) as limited:
        statuses = [(await post_turn(limited, make_wav())).status_code for _ in range(3)]
    assert statuses == [200, 200, 429]


async def test_static_ui_is_served_same_origin(client: httpx.AsyncClient) -> None:
    index = await client.get("/")
    assert index.status_code == 200
    assert index.headers["content-type"].startswith("text/html")
    assert "<title>Saathi</title>" in index.text

    script = await client.get("/js/main.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]


async def test_static_mount_does_not_serve_files_outside_the_static_dir(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get("/js/../../app.py")).status_code == 404
    assert (await client.get("/%2e%2e/app.py")).status_code == 404


async def test_healthz_needs_no_auth_and_no_upstream(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not upstream.calls  # a probe must never reach Gnani
