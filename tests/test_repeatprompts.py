import pytest

from saathi.languages import LANGUAGES
from saathi.repeatprompts import REPEAT_PROMPTS, RepeatReason, repeat_prompt, repeat_reason
from saathi.rooms import Role

REASONS: tuple[RepeatReason, ...] = ("no_facts", "unverified")


@pytest.mark.parametrize("language", list(LANGUAGES))
@pytest.mark.parametrize("reason", REASONS)
def test_every_language_has_every_prompt(language: str, reason: RepeatReason) -> None:
    prompt = repeat_prompt(language, reason)
    assert prompt is not None and prompt.text.strip()
    # English is the source; only the author's bn and hi are reviewed; the rest is machine output.
    reviewed = language in ("bn", "hi")
    expected = "source" if language == "en" else "reviewed" if reviewed else "pending"
    assert prompt.review_status == expected


def test_table_has_no_extra_languages() -> None:
    assert set(REPEAT_PROMPTS) == set(LANGUAGES)


def test_unknown_language_has_no_prompt() -> None:
    assert repeat_prompt("ur", "no_facts") is None


@pytest.mark.parametrize(
    ("verified", "fact_count", "speaker", "expected"),
    [
        (True, 2, "customer", None),
        (True, 0, "customer", "no_facts"),
        (False, 0, "customer", "unverified"),
        (False, 2, "customer", "unverified"),  # a failed check wins over having facts
        (True, 2, "rider", None),
        (True, 0, "rider", None),  # a rider has no address to give
        (False, 0, "rider", "unverified"),
        (False, 2, "rider", "unverified"),
    ],
)
def test_repeat_reason(
    verified: bool, fact_count: int, speaker: Role, expected: str | None
) -> None:
    assert repeat_reason(verified, fact_count, speaker) == expected
