"""HTTP API. Run with: uv run --no-sync uvicorn saathi.app:create_app --factory"""

import asyncio
import base64
import logging
import mimetypes
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from saathi.audio import MAX_AUDIO_BYTES, AudioError, AudioTooLargeError, wav_duration_s
from saathi.catalog_routes import catalog_router
from saathi.config import Settings, get_settings
from saathi.demo import demo_router
from saathi.demobundle import load_bundle
from saathi.gnani import GnaniClient, GnaniError, LiveSpeechUnavailable
from saathi.languages import LANGUAGES
from saathi.pipeline import (
    NoSpeechError,
    RecordingRejectedError,
    TranslationUnavailableError,
    TurnInputError,
    UnreliableTranslationError,
    run_turn,
    validate_pair,
)
from saathi.publicmode import GnaniBudget, LiveGate, ip_resolver, parse_trusted_proxies
from saathi.ratelimit import SlidingWindowLimiter
from saathi.room_routes import TimingsOut, live_paused_detail, room_router
from saathi.rooms import RoomManager
from saathi.security_headers import CspMiddleware, content_security_policy
from saathi.static_files import RevalidatedStaticFiles
from saathi.translate import RoutingTranslator, Translator

log = logging.getLogger(__name__)

# One throwaway translation per model route: (text, src, tgt) for indic-indic, en-indic, indic-en.
# The pairs are arbitrary representatives of their route; no pair is special to any role.
WARMUPS = (("আমি যাচ্ছি।", "bn", "kn"), ("I am coming.", "en", "hi"), ("मैं आ रहा हूँ।", "hi", "en"))
# Any language warms the same TTS service; English is just the shortest text to synthesize.
WARM_TTS_LANGUAGE = "en"
STATIC_DIR = Path(__file__).parent / "static"

# Windows takes MIME types from the registry, where .js is sometimes text/plain, and browsers
# refuse to run ES modules served that way.
mimetypes.add_type("text/javascript", ".js")


async def warm_up_tts(gnani: GnaniClient) -> None:
    """Make one short throwaway TTS call. A failure is logged, never fatal: the app works cold."""
    language = LANGUAGES[WARM_TTS_LANGUAGE]
    try:
        await gnani.synthesize("Ready.", language.gnani_code, language.tts_voice)
    except GnaniError as exc:
        log.warning("TTS warm-up failed (status %s); the first real call will be slow", exc.status)
    else:
        log.info("TTS warmed up")


def _socket_peer(request: Request) -> str:
    return request.client.host if request.client else "unknown"


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
    rooms: RoomManager | None = None,
) -> FastAPI:
    """Build the app. Dependencies are injectable so tests need no network, GPU or model."""
    logging.basicConfig(level=logging.INFO)  # uvicorn only configures its own loggers
    settings = settings or get_settings()
    public = settings.public_mode
    gate: LiveGate | None = None
    resolve_ip: Callable[[Request], str] = _socket_peer
    if public:
        gate = LiveGate(
            GnaniBudget(settings.budget_file, settings.daily_gnani_budget),
            settings.kill_switch,
            settings.kill_file,
        )
        resolve_ip = ip_resolver(parse_trusted_proxies(settings.trusted_proxies))
    gnani = gnani or GnaniClient(settings, before_attempt=gate)
    bundle = load_bundle(settings.demo_bundle_dir) if public else None
    # The guided demo reuses the demo-clip screen, so a loaded bundle turns that screen on.
    demo_input = settings.demo_input or bundle is not None
    default_translator = translator is None
    translator = translator or RoutingTranslator(num_beams=settings.translator_num_beams)
    limiter = SlidingWindowLimiter(settings.turn_rate_limit_per_minute)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if isinstance(translator, RoutingTranslator) and default_translator:
            # Load every model and run one throwaway translation each now: loading takes ~12 s
            # and the first generate() adds ~2.5 s of one-time CUDA setup per model, neither of
            # which a user should wait on.
            await asyncio.to_thread(translator.load)
            for text, src, tgt in WARMUPS:
                await asyncio.to_thread(translator.translate, text, src, tgt)
        if settings.warm_tts:
            await warm_up_tts(gnani)
        yield
        await gnani.aclose()

    # The interactive API docs are for development; a public host does not publish its route map.
    app = FastAPI(
        title="Saathi",
        lifespan=lifespan,
        docs_url=None if public else "/docs",
        redoc_url=None if public else "/redoc",
        openapi_url=None if public else "/openapi.json",
    )
    app.add_middleware(
        CspMiddleware, policy=content_security_policy(allow_same_origin_frames=demo_input)
    )
    if rooms is None:
        rooms = (
            RoomManager(
                max_rooms=settings.public_max_rooms,
                idle_ttl_s=settings.room_idle_ttl_s,
                hard_ttl_s=settings.room_hard_ttl_s,
            )
            if public
            else RoomManager(max_rooms=settings.max_rooms)
        )
    app.include_router(
        room_router(
            rooms,
            gnani,
            translator,
            settings.room_rate_limit_per_minute,
            settings.turn_rate_limit_per_minute,
            settings.reply_rate_limit_per_minute,
            demo_input=demo_input,
            masking_mode=settings.masking_mode,
            client_ip=resolve_ip,
            hourly_create_limit=settings.room_creates_per_hour if public else None,
            max_upload_bytes=settings.max_upload_bytes if public else MAX_AUDIO_BYTES,
            bundle=bundle,
            public_base_url=settings.public_base_url,
        )
    )

    # The single-phone page posts to /turn, which public mode switches off: not offered there.
    app.include_router(catalog_router(demo_input, solo_page=not public))
    if demo_input:
        app.include_router(demo_router(settings.demo_clips_dir))

    @app.get("/healthz")
    async def healthz() -> dict[str, str | bool]:
        # Liveness only: it touches no dependency (not Gnani, not the translator) so a probe
        # cannot spend credits or fail because an upstream is down. In public mode it also says
        # whether live calls are on, read from local state only.
        if gate is None:
            return {"status": "ok"}
        return {"status": "ok", "live": gate.live()}

    async def turn(
        request: Request,
        audio: Annotated[UploadFile, File()],
        src: Annotated[str, Form(max_length=8)],
        tgt: Annotated[str, Form(max_length=8)],
    ) -> TurnResponse:
        if not limiter.allow(resolve_ip(request)):
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
            result = await run_turn(data, src, tgt, gnani, translator, settings.masking_mode)
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
        except RecordingRejectedError as exc:
            raise HTTPException(
                400, {"code": "bad_recording", "message": "the recording cannot be used"}
            ) from exc
        except LiveSpeechUnavailable as exc:
            raise HTTPException(503, live_paused_detail(exc)) from exc
        except GnaniError as exc:
            if exc.status == 429:
                raise HTTPException(503, "speech service busy, retry shortly") from exc
            raise HTTPException(502, "speech service unavailable") from exc
        except TranslationUnavailableError as exc:
            raise HTTPException(502, "translation unavailable") from exc

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

    if public:
        # The single-phone route sits outside the room flow's guards, and the public UI never calls
        # it. Answered explicitly: left unrouted, the static mount below would say 405, not 404.
        async def turn_disabled(_: Request) -> Response:
            return Response(status_code=404)

        app.add_route("/turn", turn_disabled, methods=["POST"], include_in_schema=False)
    else:
        app.post("/turn")(turn)

    # Mounted last so it never shadows /turn. Same origin as the API, so no CORS.
    app.mount("/", RevalidatedStaticFiles(directory=STATIC_DIR, html=True), name="ui")

    return app
