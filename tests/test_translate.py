from typing import Any

import pytest
from pydantic import ValidationError

from saathi.config import Settings
from saathi.translate import (
    MAX_INPUT_CHARS,
    DegenerateTranslationError,
    IndicTrans2Translator,
    TranslationInputError,
    Translator,
    _Loaded,
    output_token_cap,
    split_sentences,
    validate_request,
)

# Static check: the IndicTrans2 class satisfies the swappable Translator protocol.
_PROTOCOL_CHECK: type[Translator] = IndicTrans2Translator


def test_split_sentences_breaks_on_danda_and_latin_punctuation() -> None:
    text = "আমি যাচ্ছি। তুমি কোথায়? ঠিক আছে."
    assert split_sentences(text) == ["আমি যাচ্ছি।", "তুমি কোথায়?", "ঠিক আছে."]


def test_split_sentences_keeps_decimal_and_ignores_blank() -> None:
    assert split_sentences("  3.5 kg  ") == ["3.5 kg"]
    assert split_sentences("   ") == []


@pytest.mark.parametrize(
    ("text", "src", "tgt"),
    [
        ("hello", "xx", "kn"),  # unknown source
        ("hello", "bn", "xx"),  # unknown target
        ("hello", "bn", "bn"),  # same language
        ("a" * (MAX_INPUT_CHARS + 1), "bn", "kn"),  # too long
    ],
)
def test_validate_request_rejects_bad_input(text: str, src: str, tgt: str) -> None:
    with pytest.raises(TranslationInputError):
        validate_request(text, src, tgt)


def test_blank_text_returns_empty_without_loading_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    translator = IndicTrans2Translator()

    def fail_load() -> None:
        raise AssertionError("model must not load for blank input")

    monkeypatch.setattr(translator, "load", fail_load)
    assert translator.translate("   ", "bn", "kn") == ""


@pytest.mark.parametrize("beams", [0, 11, -1])
def test_num_beams_out_of_range_is_rejected(beams: int) -> None:
    with pytest.raises(ValueError, match="num_beams"):
        IndicTrans2Translator(num_beams=beams)


def test_settings_num_beams_default_and_bounds() -> None:
    assert Settings(gnani_api_key="k").translator_num_beams == 1  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Settings(gnani_api_key="k", translator_num_beams=0)  # type: ignore[arg-type]


# --- Output bounding and the EOS signal, with a fake model (no GPU) ---

EOS = 2


class _Batch(dict[str, Any]):
    def to(self, _device: str) -> "_Batch":
        return self


class _FakeTokenizer:
    eos_token_id = EOS

    def __init__(self, input_len: int) -> None:
        self.input_len = input_len

    def __call__(self, batch: list[str], **_: Any) -> _Batch:
        import torch

        return _Batch(input_ids=torch.ones(len(batch), self.input_len, dtype=torch.long))

    def batch_decode(self, rows: Any, **_: Any) -> list[str]:
        return [f"row{i}" for i in range(len(rows))]


class _FakeProcessor:
    def preprocess_batch(self, sentences: list[str], **_: Any) -> list[str]:
        return sentences

    def postprocess_batch(self, decoded: list[str], **_: Any) -> list[str]:
        return decoded


# The real decoder starts every row with the EOS id, so fake rows do too.
class _FakeModel:
    def __init__(self, rows: list[list[int]]) -> None:
        self.rows = rows
        self.kwargs: dict[str, Any] = {}

    def generate(self, **kwargs: Any) -> Any:
        import torch

        self.kwargs = kwargs
        return torch.tensor(self.rows)


def _translator_with(
    rows: list[list[int]], input_len: int
) -> tuple[IndicTrans2Translator, _FakeModel]:
    translator = IndicTrans2Translator()
    model = _FakeModel(rows)
    translator._loaded = _Loaded(model, _FakeTokenizer(input_len), _FakeProcessor(), "cpu")
    return translator, model


@pytest.mark.parametrize(("input_len", "cap"), [(5, 20), (20, 50), (200, 256)])
def test_generation_is_capped_relative_to_input_length(input_len: int, cap: int) -> None:
    translator, model = _translator_with([[EOS, 7, EOS]], input_len)
    assert translator.translate("a", "bn", "kn") == "row0"
    assert model.kwargs["max_new_tokens"] == cap
    assert "max_length" not in model.kwargs


def test_row_without_eos_raises_degenerate() -> None:
    translator, _ = _translator_with([[EOS, 7, 8, 9]], 1)
    with pytest.raises(DegenerateTranslationError):
        translator.translate("a", "bn", "kn")


def test_one_unfinished_row_in_a_batch_raises_even_if_others_finish() -> None:
    translator, _ = _translator_with([[EOS, 7, EOS, 0], [EOS, 7, 8, 9]], 1)
    with pytest.raises(DegenerateTranslationError):
        translator.translate("a. b.", "bn", "kn")


def test_padded_shorter_row_with_eos_is_fine() -> None:
    translator, _ = _translator_with([[EOS, 7, EOS, 0], [EOS, 7, 8, EOS]], 1)
    assert translator.translate("a. b.", "bn", "kn") == "row0 row1"


def test_stats_report_token_counts_without_raising_when_capped() -> None:
    translator, _ = _translator_with([[EOS, 7, EOS, 0], [EOS, 7, 8, 9]], 4)
    result = translator.translate_with_stats("a. b.", "bn", "kn")
    assert result.capped
    assert result.longest_input_tokens == 4
    assert result.longest_output_tokens == 3  # the unfinished row: every generated column
    assert result.cap == 18


def test_stats_count_tokens_up_to_and_including_the_first_eos() -> None:
    translator, _ = _translator_with([[EOS, 7, EOS, 0], [EOS, 7, 8, EOS]], 1)
    result = translator.translate_with_stats("a. b.", "bn", "kn")
    assert not result.capped
    assert result.longest_output_tokens == 3


def test_stats_for_blank_text_are_empty() -> None:
    result = IndicTrans2Translator().translate_with_stats("  ", "bn", "kn")
    assert result.text == "" and not result.capped


# --- Real-model tests: `uv run pytest -m model` (GPU, cached weights) ---

# Unicode blocks of each target script, to catch a model that answers in the wrong language.
SCRIPT_RANGES = {"bn": (0x0980, 0x09FF), "kn": (0x0C80, 0x0CFF),
                 "hi": (0x0900, 0x097F), "ta": (0x0B80, 0x0BFF)}  # fmt: skip
SENTENCES = {
    "bn": "আমি আজ বাজারে যাচ্ছি।",
    "kn": "ನಾನು ಇಂದು ಮಾರುಕಟ್ಟೆಗೆ ಹೋಗುತ್ತಿದ್ದೇನೆ.",
    "hi": "मैं आज बाज़ार जा रहा हूँ।",
    "ta": "நான் இன்று சந்தைக்குப் போகிறேன்.",
}


def script_share(text: str, lang: str) -> float:
    low, high = SCRIPT_RANGES[lang]
    letters = [c for c in text if c.isalpha()]
    return sum(low <= ord(c) <= high for c in letters) / max(len(letters), 1)


@pytest.fixture(scope="module")
def real_translator() -> IndicTrans2Translator:
    translator = IndicTrans2Translator()
    translator.load()
    return translator


@pytest.mark.model
@pytest.mark.parametrize(("src", "tgt"), [("bn", "kn"), ("kn", "bn"), ("hi", "ta"), ("ta", "hi")])
def test_real_model_translates_into_target_script(
    real_translator: IndicTrans2Translator, src: str, tgt: str
) -> None:
    result = real_translator.translate(SENTENCES[src], src, tgt)
    assert result
    assert script_share(result, tgt) > 0.9


@pytest.mark.model
def test_real_model_golden_bengali_to_kannada(real_translator: IndicTrans2Translator) -> None:
    # Output recorded from the pinned stack (transformers 4.46.3, greedy); fails if a dependency
    # change shifts translation behaviour.
    assert real_translator.translate(SENTENCES["bn"], "bn", "kn") == "ನಾನು ಇಂದು ಮಾರುಕಟ್ಟೆಗೆ ಹೋಗುತ್ತಿದ್ದೇನೆ."


@pytest.mark.model
def test_real_model_translates_multiple_sentences_in_one_call(
    real_translator: IndicTrans2Translator,
) -> None:
    result = real_translator.translate(f"{SENTENCES['bn']} {SENTENCES['bn']}", "bn", "kn")
    assert result.count("ಮಾರುಕಟ್ಟೆ") == 2


# The STT transcript from the phone check (first two words misheard) that sent greedy decoding
# into a "ಆ ಚಿಕ್ಕ ಚಿಕ್ಕ ..." loop up to the length cap.
REST = "আমায় ভালো রাখো আমায় এই যন্ত্রণার জ্বালা দিও না ঠিক করো আমায় একটা বড় চাকরি দাও প্রিপারেশনটা ভালো করে করাও"
GARBLED_TRANSCRIPT = f"সেই শর্ট {REST}"
GROUND_TRUTH = f"হে ঈশ্বর {REST}"


@pytest.mark.model
def test_real_model_runaway_transcript_is_flagged(
    real_translator: IndicTrans2Translator,
) -> None:
    # No wall-clock assertion: on battery the same call takes 10 s or more. The bound is covered
    # deterministically by test_output_token_cap_*.
    with pytest.raises(DegenerateTranslationError):
        real_translator.translate(GARBLED_TRANSCRIPT, "bn", "kn")


@pytest.mark.parametrize(
    ("input_tokens", "limit", "expected"),
    [(0, 256, 10), (33, 256, 76), (100, 256, 210), (200, 256, 256)],
)
def test_output_token_cap_is_twice_the_input_plus_slack_within_the_model_limit(
    input_tokens: int, limit: int, expected: int
) -> None:
    assert output_token_cap(input_tokens, limit) == expected


@pytest.mark.model
def test_real_model_ground_truth_sentence_translates_normally(
    real_translator: IndicTrans2Translator,
) -> None:
    result = real_translator.translate(GROUND_TRUTH, "bn", "kn")
    assert script_share(result, "kn") > 0.9
    assert len(result) < 400


LONG_BN = (
    "আমি আজ সকালে ঘুম থেকে উঠে প্রথমে চা বানিয়ে খেয়েছি, তারপর বাজারে গিয়ে অনেক ধরনের সবজি আর ফল কিনেছি, "
    "বাড়ি ফিরে রান্না করেছি এবং সবাইকে খাইয়ে বিকেলে বন্ধুদের সঙ্গে দেখা করতে গিয়েছিলাম কারণ অনেক দিন কথা হয়নি, "
    "আর রাতে সবাই মিলে একসঙ্গে বসে গল্প করেছি এবং পরের দিনের কাজের পরিকল্পনা করেছি।"
)
LONG_HI = (
    "मैं आज सुबह जल्दी उठकर सबसे पहले चाय बनाकर पी, फिर बाज़ार जाकर बहुत सारी सब्ज़ियाँ और फल खरीदे, "
    "घर लौटकर खाना बनाया और सबको खिलाया और शाम को दोस्तों से मिलने गया क्योंकि बहुत दिनों से बात नहीं हुई थी, "
    "और रात को सब मिलकर साथ बैठकर बातें कीं और अगले दिन के काम की योजना बनाई।"
)


@pytest.mark.model
@pytest.mark.parametrize(("text", "src", "tgt"), [(LONG_BN, "bn", "kn"), (LONG_HI, "hi", "ta")])
def test_real_model_long_legitimate_sentence_is_not_flagged(
    real_translator: IndicTrans2Translator, text: str, src: str, tgt: str
) -> None:
    result = real_translator.translate(text, src, tgt)
    assert script_share(result, tgt) > 0.9
