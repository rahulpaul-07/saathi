import pytest
from pydantic import ValidationError

from saathi.config import Settings
from saathi.translate import (
    MAX_INPUT_CHARS,
    IndicTrans2Translator,
    TranslationInputError,
    Translator,
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
