"""FLEURS test split: deterministic clip selection by streaming, SHA-256 pinning, manifest.

FLEURS (Google, Conneau et al. 2022) is CC BY 4.0, read speech of FLORES sentences by consented
volunteers. The audio stays in the gitignored eval/audio/; only the manifest (clip ids, hashes,
reference transcripts) is committed. The full per-language tarballs are hundreds of MB, so the
tar is streamed and reading stops once enough clips are chosen.
"""

import hashlib
import io
import json
import tarfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, cast

from saathi.languages import LANGUAGES

LICENSE = "CC BY 4.0"
DATASET_URL = "https://huggingface.co/datasets/google/fleurs"
CITATION = (
    "Conneau, A., Ma, M., Khanuja, S., Zhang, Y., Axelrod, V., Dalmia, S., Riesa, J., Rivera, C., "
    "Bapna, A. (2022). FLEURS: Few-shot Learning Evaluation of Universal Representations of "
    "Speech. arXiv:2205.12446."
)
BASE_URL = f"{DATASET_URL}/resolve/main/data"
CLIPS_PER_LANGUAGE = 10
SAMPLE_RATE = 16_000
MIN_SECONDS = 3.0
MAX_SECONDS = 30.0
MANIFEST_VERSION = 1

# One FLEURS configuration per supported language; a missing key is a bug, not a fallback.
CONFIGS: dict[str, str] = {
    "bn": "bn_in",
    "en": "en_us",
    "gu": "gu_in",
    "hi": "hi_in",
    "kn": "kn_in",
    "ml": "ml_in",
    "mr": "mr_in",
    "pa": "pa_in",
    "ta": "ta_in",
    "te": "te_in",
}


class FleursError(RuntimeError):
    """The download or a clip is not what was pinned."""


@dataclass(frozen=True)
class Row:
    sentence_id: str
    file_name: str
    raw: str
    normalized: str
    num_samples: int


@dataclass(frozen=True)
class Clip:
    lang: str
    clip_id: str
    file_name: str
    sentence_id: str
    raw: str
    normalized: str
    seconds: float
    sha256: str

    @property
    def id(self) -> str:
        return self.clip_id


def tsv_url(lang: str) -> str:
    return f"{BASE_URL}/{CONFIGS[lang]}/test.tsv"


def audio_url(lang: str) -> str:
    return f"{BASE_URL}/{CONFIGS[lang]}/audio/test.tar.gz"


def audio_path(audio_dir: Path, lang: str, file_name: str) -> Path:
    return audio_dir / lang / file_name


def parse_tsv(text: str) -> list[Row]:
    """Rows of test.tsv: id, file, raw text, normalized text, phonemes, num_samples, gender."""
    rows: list[Row] = []
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) < 6:
            raise FleursError(f"unexpected tsv row with {len(fields)} fields")
        rows.append(Row(fields[0], fields[1], fields[2], fields[3], int(fields[5])))
    return rows


def eligible(rows: list[Row]) -> dict[str, Row]:
    """Rows in the length window, one per sentence (the first listed), keyed by file name."""
    chosen: dict[str, Row] = {}
    seen: set[str] = set()
    for row in rows:
        seconds = row.num_samples / SAMPLE_RATE
        if not MIN_SECONDS <= seconds <= MAX_SECONDS or row.sentence_id in seen:
            continue
        seen.add(row.sentence_id)
        chosen[row.file_name] = row
    return chosen


def select_from_tar(
    stream: BinaryIO, candidates: dict[str, Row], count: int
) -> Iterator[tuple[Row, bytes]]:
    """The first `count` candidate clips in archive order; stops reading as soon as it has them.

    Archive order is fixed by the dataset, so the choice cannot be steered by listening.
    """
    if count <= 0:
        return
    taken = 0
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for member in archive:
            row = candidates.get(Path(member.name).name)
            handle = archive.extractfile(member) if row and member.isfile() else None
            if row is None or handle is None:
                continue
            yield row, handle.read()
            taken += 1
            if taken == count:
                return


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_clip(lang: str, row: Row, data: bytes) -> Clip:
    return Clip(
        lang=lang,
        clip_id=f"{lang}-{Path(row.file_name).stem}",
        file_name=row.file_name,
        sentence_id=row.sentence_id,
        raw=row.raw,
        normalized=row.normalized,
        seconds=round(row.num_samples / SAMPLE_RATE, 2),
        sha256=sha256_bytes(data),
    )


def write_manifest(path: Path, clips: list[Clip]) -> None:
    body = {
        "version": MANIFEST_VERSION,
        "dataset": DATASET_URL,
        "license": LICENSE,
        "citation": CITATION,
        "clips": [asdict(clip) for clip in clips],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> list[Clip]:
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("version") != MANIFEST_VERSION or body.get("license") != LICENSE:
        raise FleursError("manifest version or license does not match this code")
    clips = [Clip(**item) for item in body["clips"]]
    unknown = {clip.lang for clip in clips} - set(LANGUAGES)
    if unknown:
        raise FleursError(f"manifest names unsupported languages: {sorted(unknown)}")
    return clips


def verify_clip(clip: Clip, data: bytes) -> None:
    if sha256_bytes(data) != clip.sha256:
        raise FleursError(f"{clip.clip_id}: audio does not match the pinned SHA-256")


def open_stream(chunks: Iterator[bytes]) -> BinaryIO:
    """A readable file object over a streamed HTTP body. The cast is needed because typeshed
    types BufferedReader as a BinaryIO only through its raw wrapper's generic base."""
    return cast(BinaryIO, io.BufferedReader(IterStream(chunks)))


class IterStream(io.RawIOBase):
    """Adapts an iterator of byte chunks to a raw readable stream."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = chunks
        self._buffer = b""

    def readable(self) -> bool:
        return True

    # typeshed declares readinto on a private Buffer protocol that bytearray/memoryview satisfy.
    def readinto(self, target: bytearray | memoryview) -> int:  # type: ignore[override]
        while not self._buffer:
            chunk = next(self._chunks, b"")
            if not chunk:
                return 0
            self._buffer = chunk
        size = min(len(target), len(self._buffer))
        target[:size] = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return size
