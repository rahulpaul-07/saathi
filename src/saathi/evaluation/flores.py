"""FLORES-200 devtest: download check, extraction of four files, deterministic sampling.

FLORES-200 is CC BY-SA 4.0 (Meta AI / NLLB team). The files stay in a gitignored folder; only
sentence indices and results are committed.
"""

import hashlib
import tarfile
from pathlib import Path

from saathi.languages import LANGUAGES

FLORES_URL = "https://dl.fbaipublicfiles.com/nllb/flores200_dataset.tar.gz"
# Trust-on-first-use pin: computed on the first download, then enforced on every later one.
FLORES_SHA256 = "b8b0b76783024b85797e5cc75064eb83fc5288b41e9654dabc7be6ae944011f6"
ARCHIVE_ROOT = "./flores200_dataset"  # members are stored with a leading "./"
DEVTEST_SENTENCES = 1012


class FloresError(RuntimeError):
    """The archive or an extracted file is not what was pinned."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def devtest_file(data_dir: Path, lang: str) -> Path:
    return data_dir / f"{LANGUAGES[lang].indictrans_code}.devtest"


def extract_devtest(archive: Path, data_dir: Path, *, expected_sha256: str) -> None:
    """Extract only the devtest file of each supported language (never `extractall`)."""
    if expected_sha256 and sha256_of(archive) != expected_sha256:
        raise FloresError("FLORES archive does not match the pinned SHA256")
    data_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        for lang, info in LANGUAGES.items():
            name = f"{ARCHIVE_ROOT}/devtest/{info.indictrans_code}.devtest"
            try:
                member = tar.extractfile(name)
            except KeyError:
                member = None
            if member is None:
                raise FloresError(f"{name} is missing from the archive")
            devtest_file(data_dir, lang).write_bytes(member.read())


def load_devtest(data_dir: Path, lang: str) -> list[str]:
    path = devtest_file(data_dir, lang)
    if not path.exists():
        raise FloresError(f"{path} not found; run scripts/fetch_flores.py")
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != DEVTEST_SENTENCES:
        raise FloresError(f"{path.name} has {len(lines)} lines, expected {DEVTEST_SENTENCES}")
    return lines


def sample_indices(total: int, count: int) -> list[int]:
    """`count` evenly spaced indices over `total` sentences: deterministic and spread out."""
    if not 1 <= count <= total:
        raise ValueError("count must be between 1 and total")
    return [i * total // count for i in range(count)]
