import pytest

from saathi.evaluation.metrics import bootstrap_mean_ci, cer, chrf_pp, normalize, percentile
from saathi.evaluation.startclip import HeadTail, head_tail_misses


def test_normalize_strips_punctuation_folds_case_and_composes() -> None:
    assert normalize("Hello,  World!") == "hello world"
    assert normalize("আমি ভালো।") == "আমি ভালো"
    assert normalize("é") == "é"  # NFC
    assert normalize("a-b") == "a b"


def test_cer_ignores_punctuation_and_counts_substitutions() -> None:
    assert cer("আমি, ভালো।", "আমি ভালো") == 0
    assert cer("abd", "abc") == pytest.approx(1 / 3)


def test_cer_rejects_an_empty_reference() -> None:
    with pytest.raises(ValueError):
        cer("abc", "...")


def test_percentile_interpolates_and_rejects_bad_input() -> None:
    assert percentile([4, 1, 3, 2], 50) == 2.5
    assert percentile([1, 2, 3, 4], 95) == pytest.approx(3.85)
    assert percentile([7], 95) == 7
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile([1], 101)


def test_bootstrap_ci_brackets_the_mean_is_repeatable_and_tightens_with_agreement() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    mean, low, high = bootstrap_mean_ci(values)
    assert mean == 3.5 and low < mean < high
    assert bootstrap_mean_ci(values) == (mean, low, high)
    assert bootstrap_mean_ci([2.0] * 6) == (2.0, 2.0, 2.0)
    with pytest.raises(ValueError):
        bootstrap_mean_ci([])


def test_chrf_pp_is_100_for_identical_text_and_checks_lengths() -> None:
    sentences = ["the quick brown fox jumps", "over the lazy dog today"]
    assert chrf_pp(sentences, sentences) == pytest.approx(100)
    assert chrf_pp(["zzz qqq"], ["the quick brown fox"]) < 20
    with pytest.raises(ValueError):
        chrf_pp(["a"], ["a", "b"])


def test_head_tail_counts_a_garbled_start() -> None:
    result = head_tail_misses("a b c d e", "x y c d e")
    assert (result.head_words, result.head_missed) == (2, 2)
    assert (result.tail_words, result.tail_missed) == (3, 0)


def test_head_tail_one_dropped_tail_word_does_not_shift_the_rest() -> None:
    result = head_tail_misses("a b c d e f", "a b c e f")
    assert result.head_missed == 0
    assert result.tail_missed == 1


def test_head_tail_short_reference_and_aggregation() -> None:
    short = head_tail_misses("a", "a")
    assert (short.head_words, short.tail_words) == (1, 0)
    total = head_tail_misses("a b c d", "x b c d") + head_tail_misses("a b c d", "a b c d")
    assert total == HeadTail(4, 1, 4, 0)
    assert total.head_rate == 0.25 and total.tail_rate == 0
    assert HeadTail().head_rate == 0
