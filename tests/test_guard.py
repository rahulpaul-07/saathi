import pytest

from saathi.guard import has_repeated_phrase

LONG_VARIED = (
    "ನಾನು ಇಂದು ಮಾರುಕಟ್ಟೆಗೆ ಹೋಗಿ ತರಕಾರಿ ಮತ್ತು ಹಣ್ಣುಗಳನ್ನು ಖರೀದಿಸಿ, ನಂತರ ಮನೆಗೆ ಬಂದು "
    "ಅಡುಗೆ ಮಾಡಿ ಎಲ್ಲರಿಗೂ ಬಡಿಸಿದೆ ಮತ್ತು ಸಂಜೆ ಸ್ನೇಹಿತರನ್ನು ಭೇಟಿಯಾದೆ."
)


@pytest.mark.parametrize(
    "text",
    ["ಬೇಗ ಬೇಗ", "ধীরে ধীরে", "না না না", "no no no", LONG_VARIED, "", "   "],
)
def test_legitimate_text_passes(text: str) -> None:
    assert not has_repeated_phrase(text)


@pytest.mark.parametrize("size", [1, 2, 3])
def test_phrase_repeated_three_times_passes_and_four_fails(size: int) -> None:
    phrase = ["alpha", "beta", "gamma"][:size]
    assert not has_repeated_phrase(" ".join(phrase * 3))
    assert has_repeated_phrase(" ".join(phrase * 4))


def test_alternating_loop_is_caught() -> None:
    assert has_repeated_phrase("ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ")


def test_loop_after_normal_prefix_and_with_punctuation_is_caught() -> None:
    assert has_repeated_phrase("ಆ ಚಿಕ್ಕ, ಚಿಕ್ಕ, ಚಿಕ್ಕ. ಚಿಕ್ಕ! ಚಿಕ್ಕ")
    assert has_repeated_phrase("the start x, y. x, y. x, y. x, y.")


def test_non_consecutive_repeats_pass() -> None:
    assert not has_repeated_phrase("a b a c a d a e a f")
