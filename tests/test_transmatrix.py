"""Aggregation for the translation-safety matrix. Pure functions, no model."""

from saathi.evaluation.transmatrix import (
    ArmTally,
    CellTally,
    cell_from_json,
    digit_survival,
    format_grid,
    merge,
)


def test_digit_survival_counts_digits_kept_as_digits() -> None:
    assert digit_survival("flat 402, gate 2", "फ्लैट 402, गेट 2") == (2, 2)
    assert digit_survival("flat 402, gate 2", "फ्लैट 402") == (1, 2)


def test_a_number_spelled_out_counts_as_lost_and_indic_digits_fold() -> None:
    assert digit_survival("flat 402", "flat four hundred and two") == (0, 1)
    assert digit_survival("फ्लैट ४०२", "flat 402") == (1, 1)


def test_no_digits_in_the_source_is_zero_of_zero() -> None:
    assert digit_survival("second cross", "ಎರಡನೇ ಕ್ರಾಸ್") == (0, 0)
    assert ArmTally().digit_survival is None
    assert ArmTally().recall is None


def test_recall_and_json_round_trip() -> None:
    cell = CellTally(utterances=4, fallbacks=1)
    assert cell.plain is not None and cell.masked is not None
    cell.plain.tp, cell.plain.fn = 3, 1
    cell.masked.tp, cell.masked.fn, cell.masked.failed = 4, 0, 1
    data = cell.to_json()
    assert data["plain"]["recall"] == 0.75  # type: ignore[index]
    again = cell_from_json(data)  # type: ignore[arg-type]
    assert again.masked is not None and again.masked.failed == 1
    assert again.fallbacks == 1 and again.utterances == 4


def test_merge_sums_every_counter() -> None:
    a, b = CellTally(utterances=1, fallbacks=1), CellTally(utterances=2)
    assert a.plain is not None and b.plain is not None
    a.plain.tp, b.plain.tp, b.plain.fn = 1, 2, 1
    total = merge([a, b])
    assert (total.utterances, total.fallbacks) == (3, 1)
    assert total.plain is not None and total.plain.recall == 0.75


def test_grid_marks_missing_pairs_and_the_diagonal() -> None:
    cell = CellTally(utterances=1)
    assert cell.masked is not None
    cell.masked.tp = 1
    grid = format_grid(("en", "kn"), {"en>kn": cell}, "masked")
    rows = grid.splitlines()
    assert rows[0] == "| src \\ tgt | en | kn |"
    assert rows[2] == "| en | - | 1.00 |"
    assert rows[3] == "| kn | - | - |"
