"""Convert phone voice-recorder files to 16 kHz mono 16-bit WAV with ffmpeg (no credits spent).

  convert_recording.py <input> <output.wav> [--force]
  convert_recording.py --batch <indir> <outdir> [--force]   g01.m4a -> outdir/g01.wav
  convert_recording.py --street <input> [<output.wav>]      street bed: >= 30 s, no 60 s cap;
                                                            default eval/audio/noise/street.wav

An existing output is never overwritten unless --force is given. Output is checked with the same
rules the evaluation applies (speech 1-60 s; street bed at least 30 s).
"""

import argparse
import sys
from pathlib import Path

from saathi.evaluation.convert import ConvertError, convert_batch, convert_file

ROOT = Path(__file__).resolve().parent.parent
STREET = ROOT / "eval" / "audio" / "noise" / "street.wav"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("paths", nargs="+", type=Path, help="<input> <output> (see modes above)")
    parser.add_argument("--batch", action="store_true", help="paths are <indir> <outdir>")
    parser.add_argument("--street", action="store_true", help="write the street-noise bed")
    parser.add_argument("--force", action="store_true", help="overwrite existing outputs")
    args = parser.parse_args(argv)
    if args.batch and args.street:
        parser.error("--batch and --street cannot be combined")
    expected = 1 if args.street else 2
    if len(args.paths) not in (expected, 2):
        parser.error(f"expected {expected} path(s) for this mode, got {len(args.paths)}")
    try:
        if args.batch:
            return _batch(args.paths[0], args.paths[1], args.force)
        output = args.paths[1] if len(args.paths) == 2 else STREET
        seconds = convert_file(args.paths[0], output, force=args.force, street=args.street)
    except ConvertError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {output} ({seconds:.1f} s, 16 kHz mono 16-bit)")
    return 0


def _batch(indir: Path, outdir: Path, force: bool) -> int:
    result = convert_batch(indir, outdir, force=force)
    for name, seconds in result.converted.items():
        print(f"wrote {outdir / name} ({seconds:.1f} s)")
    for name, reason in result.failed.items():
        print(f"FAILED {name}: {reason}", file=sys.stderr)
    print(f"{len(result.converted)} converted, {len(result.failed)} failed")
    return 1 if result.failed or not result.converted else 0


if __name__ == "__main__":
    sys.exit(main())
