"""Download FLORES-200 and extract the devtest file of each supported language.

Usage: uv run --no-sync python scripts/fetch_flores.py
No Gnani calls. Writes under eval/data/ (gitignored). FLORES-200 is CC BY-SA 4.0 (Meta AI).
"""

from pathlib import Path

import httpx

from saathi.evaluation.flores import (
    FLORES_SHA256,
    FLORES_URL,
    extract_devtest,
    load_devtest,
    sha256_of,
)
from saathi.languages import EVALUATED_LANGUAGES

DATA_DIR = Path("eval/data")
ARCHIVE = DATA_DIR / "flores200_dataset.tar.gz"


def download() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", FLORES_URL, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        with ARCHIVE.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)


def main() -> None:
    if not ARCHIVE.exists():
        print(f"downloading {FLORES_URL}")
        download()
    digest = sha256_of(ARCHIVE)
    print(f"sha256 {digest}")
    if not FLORES_SHA256:
        print("FLORES_SHA256 is not pinned yet: copy the hash above into evaluation/flores.py")
    extract_devtest(ARCHIVE, DATA_DIR, expected_sha256=FLORES_SHA256)
    for lang in EVALUATED_LANGUAGES:
        print(f"{lang}: {len(load_devtest(DATA_DIR, lang))} devtest sentences")


if __name__ == "__main__":
    main()
