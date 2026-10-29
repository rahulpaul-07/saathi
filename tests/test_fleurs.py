import io
import os
import tarfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from saathi.evaluation.fleurs import (
    CONFIGS,
    FleursError,
    Row,
    eligible,
    load_manifest,
    make_clip,
    open_stream,
    parse_tsv,
    select_from_tar,
    verify_clip,
    write_manifest,
)
from saathi.languages import LANGUAGES

SECONDS_5 = 5 * 16_000


def tsv_line(sentence: str, file_name: str, samples: int = SECONDS_5) -> str:
    return "\t".join([sentence, file_name, "Raw text.", "raw text", "r a w", str(samples), "MALE"])


def make_tar(names: list[str], size: int = 0) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in names:
            payload = os.urandom(size) if size else f"audio-{name}".encode()
            info = tarfile.TarInfo(f"test/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_every_supported_language_has_a_fleurs_config() -> None:
    assert set(CONFIGS) == set(LANGUAGES)


def test_parse_tsv_reads_text_and_length() -> None:
    [row] = parse_tsv(tsv_line("7", "a.wav"))
    assert row == Row("7", "a.wav", "Raw text.", "raw text", SECONDS_5)


def test_parse_tsv_rejects_a_malformed_row() -> None:
    with pytest.raises(FleursError):
        parse_tsv("only\tthree\tfields")


def test_eligible_drops_too_short_too_long_and_repeated_sentences() -> None:
    rows = parse_tsv(
        "\n".join(
            [
                tsv_line("1", "ok.wav"),
                tsv_line("1", "same-sentence.wav"),
                tsv_line("2", "short.wav", 16_000),
                tsv_line("3", "long.wav", 40 * 16_000),
            ]
        )
    )
    assert list(eligible(rows)) == ["ok.wav"]


def test_selection_follows_archive_order() -> None:
    names = ["c.wav", "a.wav", "b.wav", "d.wav"]
    candidates = {name: Row(name, name, "", "", SECONDS_5) for name in names}
    del candidates["a.wav"]
    stream = io.BytesIO(make_tar(names))
    chosen = [row.file_name for row, _ in select_from_tar(stream, candidates, 2)]
    assert chosen == ["c.wav", "b.wav"]


def test_selection_stops_reading_the_stream_once_it_has_enough() -> None:
    names = [f"{n}.wav" for n in range(6)]
    data = make_tar(names, size=100_000)
    chunks = [data[i : i + 65_536] for i in range(0, len(data), 65_536)]
    consumed = 0

    def feed() -> Iterator[bytes]:
        nonlocal consumed
        for chunk in chunks:
            consumed += 1
            yield chunk

    candidates = {name: Row(name, name, "", "", SECONDS_5) for name in names}
    [(row, _)] = list(select_from_tar(open_stream(feed()), candidates, 1))
    assert row.file_name == "0.wav"
    assert consumed < len(chunks)


def test_selection_reads_from_a_chunked_stream() -> None:
    data = make_tar(["a.wav", "b.wav"])
    chunks = iter([data[i : i + 7] for i in range(0, len(data), 7)])
    candidates = {"b.wav": Row("1", "b.wav", "", "", SECONDS_5)}
    [(row, audio)] = list(select_from_tar(open_stream(chunks), candidates, 5))
    assert (row.file_name, audio) == ("b.wav", b"audio-b.wav")


def test_manifest_round_trip_and_hash_check(tmp_path: Path) -> None:
    clip = make_clip("kn", Row("9", "x.wav", "Raw.", "raw", SECONDS_5), b"pcm")
    path = tmp_path / "manifest.json"
    write_manifest(path, [clip])
    assert load_manifest(path) == [clip]
    verify_clip(clip, b"pcm")
    with pytest.raises(FleursError):
        verify_clip(clip, b"tampered")


def test_manifest_with_an_unsupported_language_is_refused(tmp_path: Path) -> None:
    clip = make_clip("xx", Row("9", "x.wav", "", "", SECONDS_5), b"pcm")
    path = tmp_path / "manifest.json"
    write_manifest(path, [clip])
    with pytest.raises(FleursError):
        load_manifest(path)
