"""HTTP API. Run with: uv run --no-sync uvicorn saathi.app:create_app --factory"""

import asyncio
import base64
import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from saathi.audio import MAX_AUDIO_BYTES, AudioError, AudioTooLargeError, wav_duration_s
from saathi.config import Settings, get_settings
from saathi.gnani import GnaniClient, GnaniError
from saathi.pipeline import (
    NoSpeechError,
    TurnInputError,
    UnreliableTranslationError,
    run_turn,
    validate_pair,
)
from saathi.ratelimit import SlidingWindowLimiter
from saathi.translate import IndicTrans2Translator, Translator

log = logging.getLogger(__name__)

WARMUP_TEXT = "আমি যাচ্ছি।"
STATIC_DIR = Path(__file__).parent / "static"

# Windows takes MIME types from the registry, where .js is sometimes text/plain, and browsers
# refuse to run ES modules served that way.
mimetypes.add_type("text/javascript", ".js")


class TimingsOut(BaseModel):
    stt_ms: float
    translate_ms: float
    tts_ms: float
    total_ms: float


class TurnResponse(BaseModel):
    src: str
    tgt: str
    transcript: str
    translation: str
    audio_base64: str  # WAV, 24 kHz mono 16-bit
    audio_format: str = "wav"
    timings: TimingsOut


def create_app(
    settings: Settings | None = None,
    gnani: GnaniClient | None = None,
    translator: Translator | None = None,
) -> FastAPI:
    """Build the app. Dependencies are injectable so tests need no network, GPU or model."""
    logging.basicConfig(level=logging.INFO)  # uvicorn only configures its own loggers
    settings = settings or get_settings()
    gnani = gnani or GnaniClient(settings)
    default_translator = translator is None
    translator = translator or IndicTrans2Translator(num_beams=settings.translator_num_beams)
    limiter = SlidingWindowLimiter(settings.turn_rate_limit_per_minute)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if isinstance(translator, IndicTrans2Translator) and default_translator:
            # Load and run one throwaway translation now: loading takes ~12 s and the first
            # generate() adds ~2.5 s of one-time CUDA setup, neither of which a user should wait on.
            await asyncio.to_thread(translator.load)
            await asyncio.to_thread(translator.translate, WARMUP_TEXT, "bn", "kn")
        yield
        await gnani.aclose()

    app = FastAPI(title="Saathi", lifespan=lifespan)

    @app.post("/turn")
    async def turn(
        request: Request,
        audio: Annotated[UploadFile, File()],
        src: Annotated[str, Form(max_length=8)],
        tgt: Annotated[str, Form(max_length=8)],
    ) -> TurnResponse:
        client_ip = request.client.host if request.client else "unknown"
        if not limiter.allow(client_ip):
            raise HTTPException(429, "too many requests")

        # Everything below up to run_turn is free; reject bad input before any paid call.
        try:
            validate_pair(src, tgt)
            data = await audio.read(MAX_AUDIO_BYTES + 1)
            wav_duration_s(data)
        except AudioTooLargeError as exc:
            raise HTTPException(413, str(exc)) from exc
        except (TurnInputError, AudioError) as exc:
            raise HTTPException(400, str(exc)) from exc

        try:
            result = await run_turn(data, src, tgt, gnani, translator)
        except NoSpeechError as exc:
            raise HTTPException(
                422, {"code": "no_speech", "message": "no speech detected"}
            ) from exc
        except UnreliableTranslationError as exc:
            # The transcript is untrusted text from STT; clients must render it as text only.
            raise HTTPException(
                422,
                {
                    "code": "unreliable_translation",
                    "message": "could not translate reliably",
                    "transcript": exc.transcript,
                },
            ) from exc
        except GnaniError as exc:
            if exc.status == 429:
                raise HTTPException(503, "speech service busy, retry shortly") from exc
            raise HTTPException(502, "speech service unavailable") from exc

        timings = result.timings
        log.info(
            "turn %s->%s stt=%.0fms translate=%.0fms tts=%.0fms total=%.0fms",
            src,
            tgt,
            timings.stt_ms,
            timings.translate_ms,
            timings.tts_ms,
            timings.total_ms,
        )
        return TurnResponse(
            src=src,
            tgt=tgt,
            transcript=result.transcript,
            translation=result.translation,
            audio_base64=base64.b64encode(result.audio).decode("ascii"),
            timings=TimingsOut(**vars(timings)),
        )

    # Mounted last so it never shadows /turn. Same origin as the API, so no CORS.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

    return app
