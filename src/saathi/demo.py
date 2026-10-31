"""Demo input mode: prepared WAV clips a participant can send instead of the microphone.

Off by default (SAATHI_DEMO_INPUT). The clips are Gnani TTS audio mixed with licensed street
noise by scripts/make_demo_clips.py; they are listed in a manifest next to the files, and the
routes only ever serve ids found in that manifest, so a request cannot name a path.
"""

import json
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import BaseModel, ValidationError

from saathi.languages import LANGUAGES

log = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
ClipIdPath = Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")]


class DemoClip(BaseModel):
    id: str
    lang: str
    label: str  # English
    label_local: str = ""  # the same name in the clip's own language; empty when not written yet


def load_demo_clips(directory: Path) -> dict[str, DemoClip]:
    """The clips listed in the manifest whose file exists; empty when there is no manifest."""
    manifest = directory / MANIFEST_NAME
    if not manifest.is_file():
        log.warning("demo input is on but %s does not exist", manifest)
        return {}
    try:
        clips = [DemoClip(**item) for item in json.loads(manifest.read_text("utf-8"))["clips"]]
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        log.warning("demo manifest %s is not valid; no demo clips offered", manifest)
        return {}
    return {
        clip.id: clip
        for clip in clips
        if clip.lang in LANGUAGES and (directory / f"{clip.id}.wav").is_file()
    }


def demo_router(directory: Path) -> APIRouter:
    router = APIRouter()
    clips = load_demo_clips(directory)

    @router.get("/demo/clips")
    async def list_clips() -> list[DemoClip]:
        return list(clips.values())

    @router.get("/demo/clips/{clip_id}.wav")
    async def clip_audio(clip_id: ClipIdPath) -> Response:
        if clip_id not in clips:
            raise HTTPException(404, "clip not found")
        data = (directory / f"{clip_id}.wav").read_bytes()
        return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    return router
