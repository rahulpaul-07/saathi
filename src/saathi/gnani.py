"""Thin client for the Gnani Vachana speech APIs (Prisma v2.5 STT, Timbre v2.5 TTS).

Request shapes follow docs.gnani.ai/api/STT/speech-to-text and /api/TTS/tts-inference.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from saathi.audio import AudioError, finalize_streaming_wav
from saathi.config import Settings
from saathi.loudness import normalize_or_passthrough

log = logging.getLogger(__name__)

STT_PATH = "/stt/v3"
TTS_PATH = "/api/v1/tts/inference"
TTS_MODEL = "timbre-v2.5"
RETRY_WAIT_S = 1.0


class GnaniError(Exception):
    """Upstream speech API failure. `status` is the upstream HTTP status, 0 for transport errors."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class GnaniClient:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retry_wait_s: float = RETRY_WAIT_S,
    ) -> None:
        self._sleep = sleep
        self._retry_wait_s = retry_wait_s
        self._client = client or httpx.AsyncClient(
            base_url=settings.gnani_base_url,
            timeout=settings.gnani_timeout_s,
            headers={"X-API-Key-ID": settings.gnani_api_key.get_secret_value()},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(self, audio: bytes, filename: str, language_code: str) -> str:
        response = await self._post(
            STT_PATH,
            files={"audio_file": (filename, audio)},
            data={"language_code": language_code},
        )
        body = response.json()
        if not body.get("success"):
            raise GnaniError("STT returned success=false", response.status_code)
        return str(body["transcript"])

    async def synthesize(
        self,
        text: str,
        language_code: str,
        voice: str,
        *,
        sample_rate: int = 24000,
        container: str = "wav",
    ) -> bytes:
        response = await self._post(
            TTS_PATH,
            json={
                "text": text,
                "model": TTS_MODEL,
                "voice": voice,
                "language": language_code,
                "audio_config": {
                    "sample_rate": sample_rate,
                    "num_channels": 1,
                    "sample_width": 2,
                    "encoding": "linear_pcm",
                    "container": container,
                },
            },
        )
        if container != "wav":
            return response.content
        try:
            wav = finalize_streaming_wav(response.content)
        except AudioError as exc:
            log.error("Gnani TTS returned an invalid WAV: %s", exc)
            raise GnaniError("speech service returned invalid audio") from exc
        # The single place TTS audio is produced: turns and quick replies both come through here.
        return await asyncio.to_thread(normalize_or_passthrough, wav)

    async def _post(self, path: str, **kwargs: object) -> httpx.Response:
        """One request, retried once after a timeout or a 5xx (a gateway blip, as seen live).
        A 429 is not retried: that is Gnani's rate limit and the caller backs off. Only the status
        is logged; the response body may echo what was said."""
        for attempt in range(2):
            try:
                response = await self._client.post(path, **kwargs)  # type: ignore[arg-type]
            except httpx.TimeoutException as exc:
                log.warning("Gnani timeout on %s (attempt %d)", path, attempt + 1)
                if attempt == 0:
                    await self._sleep(self._retry_wait_s)
                    continue
                raise GnaniError("speech service timed out") from exc
            except httpx.HTTPError as exc:
                log.error("Gnani transport error on %s: %s", path, type(exc).__name__)
                raise GnaniError("speech service unreachable") from exc
            if response.status_code >= 500 and attempt == 0:
                log.warning("Gnani %s -> %s (attempt 1), retrying", path, response.status_code)
                await self._sleep(self._retry_wait_s)
                continue
            if response.status_code != 200:
                log.error("Gnani %s -> %s", path, response.status_code)
                raise GnaniError(
                    f"speech service error {response.status_code}", response.status_code
                )
            return response
        raise AssertionError("unreachable: the loop returns or raises")  # pragma: no cover
