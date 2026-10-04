"""Thin client for the Gnani Vachana speech APIs (Prisma v2.5 STT, Timbre v2.5 TTS).

Request shapes follow docs.gnani.ai/api/STT/speech-to-text and /api/TTS/tts-inference.
"""

import logging

import httpx

from saathi.config import Settings

log = logging.getLogger(__name__)

STT_PATH = "/stt/v3"
TTS_PATH = "/api/v1/tts/inference"
TTS_MODEL = "timbre-v2.5"


class GnaniError(Exception):
    """Upstream speech API failure. `status` is the upstream HTTP status, 0 for transport errors."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class GnaniClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
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
        return response.content

    async def _post(self, path: str, **kwargs: object) -> httpx.Response:
        try:
            response = await self._client.post(path, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            log.error("Gnani transport error on %s: %s", path, exc)
            raise GnaniError("speech service unreachable") from exc
        if response.status_code != 200:
            # Body goes to the server log only; callers get a generic message.
            log.error("Gnani %s -> %s: %s", path, response.status_code, response.text[:300])
            raise GnaniError(f"speech service error {response.status_code}", response.status_code)
        return response
