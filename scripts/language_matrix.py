"""Run the language matrix: every ordered pair of the ten languages through the guided demo.

The app is the real one in public mode, with the shipped demo bundle and the real local
IndicTrans2 translator. No Gnani call is possible: the client handed to the app refuses any use,
the dummy API key is not a credential, and the settings never read `.env`. Run it from the
repository root; it loads the translation models first (about a minute).

    uv run --no-sync python scripts/language_matrix.py

Writes eval/results/language_matrix.md and eval/results/language_matrix.json. The exit code is 0
when every pair passes, 1 when some replay failed (the report says which and why), 2 when anything
reached for Gnani.
"""

import argparse
import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from saathi.app import WARMUPS, create_app
from saathi.config import Settings
from saathi.evaluation.langmatrix import (
    GnaniForbidden,
    load_matrix_clips,
    mapping_evidence,
    pair_failures,
    render_report,
    report_json,
    run_matrix,
)
from saathi.evaluation.power import read_power_state
from saathi.evaluation.runinfo import run_metadata
from saathi.gnani import GnaniClient
from saathi.languages import LANGUAGES
from saathi.rooms import RoomManager
from saathi.translate import RoutingTranslator

CLIP_SET = Path("demo/clip_set.json")
# The limits protect a public endpoint from many callers; this run is one local caller.
UNLIMITED = 100_000


class MatrixSettings(Settings):
    """The app's settings with the `.env` file switched off: this run needs no credential, so it
    must not read one. Explicit values below still win over any variable in the environment."""

    model_config = SettingsConfigDict(env_file=None)


def build_settings(budget_file: Path) -> Settings:
    fields: dict[str, Any] = {
        "gnani_api_key": SecretStr("not-a-credential"),
        "public_mode": True,
        "budget_file": budget_file,
        "room_rate_limit_per_minute": UNLIMITED,
        "turn_rate_limit_per_minute": UNLIMITED,
        "reply_rate_limit_per_minute": UNLIMITED,
        "room_creates_per_hour": UNLIMITED,
    }
    return MatrixSettings(**fields)


async def run(languages: list[str], out_dir: Path) -> int:
    # Three INFO lines per replay would bury the progress lines; warnings still show.
    for noisy in ("httpx", "saathi.room_routes"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    with tempfile.TemporaryDirectory() as scratch:
        settings = build_settings(Path(scratch) / "budget.json")
        clips, left_out = load_matrix_clips(
            CLIP_SET, settings.demo_clips_dir, settings.demo_bundle_dir
        )
        translator = RoutingTranslator(num_beams=settings.translator_num_beams)
        print("loading the translation models ...", flush=True)
        translator.load()
        for text, src, tgt in WARMUPS:  # the app's own start-up warm-up
            translator.translate(text, src, tgt)
        manager = RoomManager(max_rooms=settings.public_max_rooms)
        gnani = GnaniForbidden()
        app = create_app(settings, cast(GnaniClient, gnani), translator, manager)
        meta = run_metadata(read_power_state(), num_beams=settings.translator_num_beams)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://saathi") as client:
            runs = await run_matrix(
                client, manager, clips, languages, progress=lambda line: print(line, flush=True)
            )

    attempts = len(gnani.attempts)
    mapping = mapping_evidence(CLIP_SET, settings.demo_clips_dir, settings.demo_bundle_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "language_matrix.md").write_text(
        render_report(
            runs,
            languages=languages,
            meta=meta,
            left_out=left_out,
            gnani_attempts=attempts,
            mapping=mapping,
        ),
        encoding="utf-8",
    )
    (out_dir / "language_matrix.json").write_text(
        json.dumps(
            report_json(
                runs, meta=meta, left_out=left_out, gnani_attempts=attempts, mapping=mapping
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    failing = pair_failures(runs)
    total = len(languages) * (len(languages) - 1)
    print(f"{total - len(failing)} of {total} ordered pairs passed; Gnani attempts: {attempts}")
    return 2 if attempts else (1 if failing else 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument(
        "--languages",
        default=",".join(sorted(LANGUAGES)),
        help="comma-separated language codes (default: all ten)",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("eval/results"))
    args = parser.parse_args()
    languages = [code.strip() for code in args.languages.split(",") if code.strip()]
    unknown = sorted(set(languages) - set(LANGUAGES))
    if unknown or len(languages) < 2:
        parser.error(f"need two or more known language codes; unknown: {unknown}")
    return asyncio.run(run(languages, args.out_dir))


if __name__ == "__main__":
    sys.exit(main())
