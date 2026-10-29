"""Fetch 10 FLEURS test clips per supported language and pin them by SHA-256.

Usage: uv run --no-sync python scripts/fetch_fleurs.py
No Gnani calls. Audio goes to eval/audio/fleurs/ (gitignored); the manifest with clip ids, hashes
and reference transcripts is eval/gold/fleurs_manifest.json (committed); the pinned SHA-256 is
of the 16-bit WAV written here, converted from FLEURS's 32-bit float. FLEURS is CC BY 4.0
(Google); see docs/EVAL.md for the attribution. The first run records the hashes; later runs
fail if a re-download differs from them.
"""

from pathlib import Path

import httpx

from saathi.evaluation.fleurs import (
    CLIPS_PER_LANGUAGE,
    CONFIGS,
    Clip,
    FleursError,
    audio_path,
    audio_url,
    eligible,
    load_manifest,
    make_clip,
    open_stream,
    parse_tsv,
    select_from_tar,
    tsv_url,
    write_manifest,
)
from saathi.evaluation.wavtools import float_wav_to_pcm16

AUDIO_DIR = Path("eval/audio/fleurs")
MANIFEST = Path("eval/gold/fleurs_manifest.json")
TIMEOUT = httpx.Timeout(60, read=120)


def fetch_language(client: httpx.Client, lang: str) -> list[Clip]:
    response = client.get(tsv_url(lang))
    response.raise_for_status()
    candidates = eligible(parse_tsv(response.text))
    clips: list[Clip] = []
    with client.stream("GET", audio_url(lang)) as body:
        body.raise_for_status()
        stream = open_stream(body.iter_raw(1 << 20))
        for row, original in select_from_tar(stream, candidates, CLIPS_PER_LANGUAGE):
            data = float_wav_to_pcm16(original)  # FLEURS ships 32-bit float; Gnani gets 16-bit
            target = audio_path(AUDIO_DIR, lang, row.file_name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            clips.append(make_clip(lang, row, data))
    if len(clips) < CLIPS_PER_LANGUAGE:
        raise FleursError(f"{lang}: only {len(clips)} eligible clips found")
    return clips


def main() -> None:
    known = load_manifest(MANIFEST) if MANIFEST.exists() else []
    pinned = {clip.clip_id: clip.sha256 for clip in known}
    fetched: list[Clip] = []
    with httpx.Client(follow_redirects=True, timeout=TIMEOUT) as client:
        for lang in CONFIGS:
            clips = fetch_language(client, lang)
            fetched.extend(clips)
            print(f"{lang}: {len(clips)} clips, {sum(c.seconds for c in clips):.0f} s")
    if pinned:
        changed = [c.clip_id for c in fetched if pinned.get(c.clip_id) != c.sha256]
        if changed or len(pinned) != len(fetched):
            raise FleursError(f"download differs from the pinned manifest: {changed[:5]}")
        print("all clips match the pinned SHA-256 values")
    else:
        write_manifest(MANIFEST, fetched)
        print(f"pinned {len(fetched)} clips in {MANIFEST}")


if __name__ == "__main__":
    main()
