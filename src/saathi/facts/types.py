from dataclasses import dataclass
from typing import Literal, get_args

FactKind = Literal["gate", "floor", "cross", "main", "block", "flat", "landmark"]
FACT_KINDS: tuple[FactKind, ...] = get_args(FactKind)

Confidence = Literal["high", "low"]


@dataclass(frozen=True)
class Fact:
    """One critical address fact found in a transcript.

    `start`/`end` are character offsets into the text that was passed to `extract_facts`. For the
    structured kinds the span covers the whole phrase ("gate number 2"); for a landmark it covers
    the landmark name only, not the word that triggered it.

    `value` is the normalized value ("2", "304", "5B", "C") for a clear reading. When the reading
    is ambiguous (digit-by-digit speech such as "one four", which may be 14 or 1 and 4) `value`
    is the words exactly as heard, `reading` holds the best candidate ("14") and the UI should
    show `value`. A landmark's `value` is always the name as heard.

    `value_start`/`value_end` cover the value alone inside the phrase ("2" in "gate number 2");
    masking replaces exactly this span. Landmarks have none. `local` is the landmark rendered in
    the listener's language, set by the pipeline after extraction; None means "not available".
    """

    kind: FactKind
    value: str
    start: int
    end: int
    heard: str
    confidence: Confidence = "high"
    ambiguous: bool = False
    reading: str | None = None
    value_start: int | None = None
    value_end: int | None = None
    local: str | None = None
