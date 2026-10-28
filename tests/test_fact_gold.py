import hashlib
import json
from collections import Counter
from pathlib import Path

from saathi.evaluation.factscore import (
    GoldFact,
    GoldUtterance,
    KindScore,
    load_gold,
    score,
    select,
)
from saathi.facts import FACT_KINDS
from saathi.languages import LANGUAGES

GOLD_PATH = Path(__file__).resolve().parent.parent / "eval" / "gold" / "directions.json"
# SHA-256 of the test split (canonical JSON). Changing a test utterance or its gold facts must be a
# deliberate act: update this value in the same commit and say why (e.g. a corrected recording).
TEST_SPLIT_SHA256 = "5bdaa25668891dbe1dce55133a4ab9250c3d51cf122e0e137fd14f4475b57852"


def test_gold_set_shape_and_split_rule() -> None:
    gold = load_gold(GOLD_PATH)
    assert len(gold) == 30
    assert len({u.id for u in gold}) == 30
    assert Counter(u.lang for u in gold) == {"en": 12, "kn": 10, "hi": 4, "bn": 4}
    assert all(u.lang in LANGUAGES for u in gold)
    assert all(f.kind in FACT_KINDS for u in gold for f in u.facts)
    for utterance in gold:  # recorded rule: dev when the id number is divisible by 3
        expected = "dev" if int(utterance.id[1:]) % 3 == 0 else "test"
        assert utterance.split == expected, utterance.id
    assert len(select(gold, "dev")) == 10 and len(select(gold, "test")) == 20
    assert {u.lang for u in select(gold, "dev")} == {"en", "kn", "hi", "bn"}


def test_test_split_is_frozen() -> None:
    raw = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    test_items = [u for u in raw["utterances"] if u["split"] == "test"]
    canonical = json.dumps(test_items, sort_keys=True, ensure_ascii=False)
    assert hashlib.sha256(canonical.encode()).hexdigest() == TEST_SPLIT_SHA256


def test_gold_texts_are_synthetic_and_small() -> None:
    # A guard, not proof: no phone numbers or e-mail addresses in a set meant to be shareable.
    for utterance in load_gold(GOLD_PATH):
        assert "@" not in utterance.text and len(utterance.text) < 200


def test_extractor_scores_on_gold_text_stay_precise() -> None:
    # Text-only and written by the extractor's author: a regression guard, not an accuracy claim.
    for split in ("dev", "test"):
        report, _ = score(select(load_gold(GOLD_PATH), split))
        assert report.overall.precision == 1.0
        assert report.overall.recall is not None and report.overall.recall >= 0.9
        assert report.all_correct >= report.utterances * 0.8


def _gold(text: str, lang: str, *facts: tuple[str, str]) -> GoldUtterance:
    return GoldUtterance(
        "g99",
        "dev",
        lang,
        text,
        tuple(GoldFact(kind, value) for kind, value in facts),  # type: ignore[arg-type]
    )


def test_scoring_counts_wrong_missed_and_ambiguous_separately() -> None:
    utterances = [
        _gold("gate 2, 3rd main", "en", ("gate", "2"), ("main", "3")),  # both right
        _gold("gate 2", "en", ("gate", "3")),  # wrong value: one fp and one fn
        _gold("second floor", "en", ("floor", "2"), ("cross", "4")),  # cross missed
        _gold("flat one four", "en", ("flat", "14")),  # ambiguous: not asserted, reading right
        _gold("Gate 2", "en", ("gate", "2")),  # case does not matter
    ]
    report, misses = score(utterances)
    kinds = report.by_kind
    gate, main, floor, cross, flat = (kinds[k] for k in ("gate", "main", "floor", "cross", "flat"))
    assert (gate.tp, gate.fp, gate.fn) == (2, 1, 1)
    assert (main.tp, floor.tp, cross.fn) == (1, 1, 1)
    assert (flat.tp, flat.fp, flat.fn) == (0, 0, 1)
    assert (flat.ambiguous, flat.ambiguous_reading_correct) == (1, 1)
    assert report.utterances == 5 and report.all_correct == 2 and len(misses) == 3
    assert gate.precision == 2 / 3 and gate.recall == 2 / 3


def test_precision_is_undefined_without_predictions() -> None:
    assert KindScore().precision is None and KindScore().recall is None
    report, _ = score([_gold("hello", "en")])
    assert report.overall.precision is None and report.all_correct == 1
