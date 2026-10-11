from saathi.evaluation.probe import (
    PLANNED_PROBE_CALLS,
    PROBE_CALL_CAP,
    PROBE_TEXTS,
    classify_token,
    classify_transcript,
)


def test_classify_token_covers_each_written_form() -> None:
    assert classify_token("2nd") == "digits"
    assert classify_token("೨") == "digits"  # Kannada digit two
    assert classify_token("gate") == "latin"
    assert classify_token("ಎರಡು") == "kannada-number-word"
    assert classify_token("ಮೂರನೇ") == "kannada-number-word"
    assert classify_token("ಗೇಟ್") == "kannada"
    assert classify_token("-") == "other"


def test_classify_transcript_groups_tokens_and_drops_plain_kannada() -> None:
    groups = classify_transcript("ಗೇಟ್ ನಂಬರ್ 2, opposite ಮೂರನೇ ಕ್ರಾಸ್")
    assert groups == {"digits": ["2"], "latin": ["opposite"], "kannada-number-word": ["ಮೂರನೇ"]}


def test_probe_plan_counts_and_cap() -> None:
    assert PLANNED_PROBE_CALLS == 8 + 14
    assert PROBE_CALL_CAP > PLANNED_PROBE_CALLS
    assert len({item.key for item in PROBE_TEXTS}) == len(PROBE_TEXTS)
