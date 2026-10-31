"""Aggregation for the translation-safety matrix (scripts/eval_translation_matrix.py).

Offline and text only. Each cell is a source language X and a target language Y: the English gold
sentence was machine-translated to X, then X to Y two ways (plain, and with numbers and loanwords
masked), then Y back to English, and the English extractor was run on that back-translation against
the gold facts. A fact lost anywhere on the way counts as lost, so a cell measures the whole
X to Y to English path, including the back-translation's own errors.
"""

from dataclasses import asdict, dataclass

from saathi.facts.text import tokenize

ARMS = ("plain", "masked")


def digit_strings(text: str) -> set[str]:
    """Every run of digits in `text`, with Indic digits folded to ASCII by the shared tokenizer."""
    return {token.key for token in tokenize(text) if token.key.isdecimal()}


def digit_survival(source: str, output: str) -> tuple[int, int]:
    """(digit runs of `source` that are still digits in `output`, digit runs in `source`).

    A number the model spelled out as a word counts as lost: the app shows digits on the chips.
    """
    wanted = digit_strings(source)
    return len(wanted & digit_strings(output)), len(wanted)


@dataclass
class ArmTally:
    tp: int = 0
    fn: int = 0
    failed: int = 0  # translation or back-translation raised; its facts count as missed
    digits_kept: int = 0
    digits_wanted: int = 0

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def digit_survival(self) -> float | None:
        return self.digits_kept / self.digits_wanted if self.digits_wanted else None


@dataclass
class CellTally:
    utterances: int = 0
    fallbacks: int = 0  # masked translations where a slot was lost (the app then speaks a summary)
    plain: ArmTally | None = None
    masked: ArmTally | None = None

    def __post_init__(self) -> None:
        self.plain = self.plain or ArmTally()
        self.masked = self.masked or ArmTally()

    def to_json(self) -> dict[str, object]:
        out = asdict(self)
        for name in ARMS:
            arm: ArmTally = getattr(self, name)
            out[name]["recall"] = arm.recall
            out[name]["digit_survival"] = arm.digit_survival
        return out


def merge(cells: list[CellTally]) -> CellTally:
    total = CellTally()
    for cell in cells:
        assert cell.plain is not None and cell.masked is not None
        total.utterances += cell.utterances
        total.fallbacks += cell.fallbacks
        for name in ARMS:
            into: ArmTally = getattr(total, name)
            part: ArmTally = getattr(cell, name)
            into.tp += part.tp
            into.fn += part.fn
            into.failed += part.failed
            into.digits_kept += part.digits_kept
            into.digits_wanted += part.digits_wanted
    return total


def cell_from_json(data: dict[str, dict[str, int] | int]) -> CellTally:
    def arm(raw: object) -> ArmTally:
        assert isinstance(raw, dict)
        return ArmTally(
            raw["tp"], raw["fn"], raw["failed"], raw["digits_kept"], raw["digits_wanted"]
        )

    utterances, fallbacks = data["utterances"], data["fallbacks"]
    assert isinstance(utterances, int) and isinstance(fallbacks, int)
    return CellTally(utterances, fallbacks, arm(data["plain"]), arm(data["masked"]))


def format_grid(
    langs: tuple[str, ...], cells: dict[str, CellTally], arm: str, metric: str = "recall"
) -> str:
    """A Markdown table, rows = source language, columns = target language."""
    lines = ["| src \\ tgt | " + " | ".join(langs) + " |", "|---|" + "---|" * len(langs)]
    for src in langs:
        row = [src]
        for tgt in langs:
            cell = cells.get(f"{src}>{tgt}")
            value = None if cell is None else getattr(getattr(cell, arm), metric)
            row.append("-" if value is None else f"{value:.2f}")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
