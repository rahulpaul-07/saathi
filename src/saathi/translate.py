"""Translation step of the pipeline.

`Translator` is the swap point: IndicTrans2 is the default, and any other engine only has to
implement `translate`. Heavy imports (torch, transformers) are deferred so that importing this
module, and the pure-logic tests, stay fast.
"""

import re
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from saathi.languages import LANGUAGES

DEFAULT_MODEL = "ai4bharat/indictrans2-indic-indic-dist-320M"
MAX_INPUT_CHARS = 2000  # a 60 s STT clip is well under this
MAX_BEAMS = 10
# Normal output is 0.9-1.2x the input in tokens (measured); a runaway loop is ~8x. 2x plus slack
# bounds a loop to a fraction of the model's 256-position limit without cutting real translations.
OUTPUT_TOKEN_RATIO = 2
OUTPUT_TOKEN_SLACK = 10

# Break after sentence-final punctuation (including the Devanagari/Bengali danda).
_SENTENCE_BREAK = re.compile(r"(?<=[।.!?])\s+")


class TranslationInputError(ValueError):
    """The caller asked for something outside what the translator supports."""


class DegenerateTranslationError(Exception):
    """The model hit its output cap without finishing: a runaway loop, not a result."""


@dataclass(frozen=True)
class TranslationResult:
    text: str
    longest_input_tokens: int
    longest_output_tokens: int  # the cap compares this against longest_input_tokens
    cap: int
    capped: bool  # at least one row hit the cap without finishing


class Translator(Protocol):
    def translate(self, text: str, src: str, tgt: str) -> str:
        """Translate `text` from language key `src` to `tgt` (keys from `LANGUAGES`)."""
        ...


def output_token_cap(longest_input_tokens: int, model_limit: int) -> int:
    """Most tokens one translation may generate: relative to the input, within the model limit."""
    return min(OUTPUT_TOKEN_RATIO * longest_input_tokens + OUTPUT_TOKEN_SLACK, model_limit)


def split_sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_BREAK.split(text.strip()) if part]


def validate_request(text: str, src: str, tgt: str) -> list[str]:
    """Check a translate call and return the sentences to translate (empty for blank text)."""
    for key in (src, tgt):
        if key not in LANGUAGES:
            raise TranslationInputError(f"unsupported language: {key!r}")
    if src == tgt:
        raise TranslationInputError("source and target language must differ")
    if len(text) > MAX_INPUT_CHARS:
        raise TranslationInputError(f"text longer than {MAX_INPUT_CHARS} characters")
    return split_sentences(text)


@dataclass
class _Loaded:
    model: Any
    tokenizer: Any
    processor: Any
    device: str


class IndicTrans2Translator:
    """IndicTrans2 indic-indic distilled model, translating directly with no English pivot."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL,
        num_beams: int = 1,
        max_length: int = 256,
    ) -> None:
        if not 1 <= num_beams <= MAX_BEAMS:
            raise ValueError(f"num_beams must be between 1 and {MAX_BEAMS}")
        self._model_name = model_name
        self._num_beams = num_beams
        self._max_length = max_length
        self._lock = threading.Lock()  # one generate() at a time; the model is not thread-safe
        self._loaded: _Loaded | None = None

    def load(self) -> _Loaded:
        """Load the model once. Call at startup so the first user turn does not pay for it."""
        with self._lock:
            if self._loaded is None:
                self._loaded = self._load_model()
            return self._loaded

    def _load_model(self) -> _Loaded:
        import torch
        from IndicTransToolkit.processor import IndicProcessor
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        tokenizer = AutoTokenizer.from_pretrained(self._model_name, trust_remote_code=True)
        # transformers 4.46 spells this `torch_dtype`; the newer `dtype` alias does not exist yet.
        model = AutoModelForSeq2SeqLM.from_pretrained(
            self._model_name, trust_remote_code=True, torch_dtype=dtype
        )
        model = model.to(device).eval()
        return _Loaded(model, tokenizer, IndicProcessor(inference=True), device)

    def translate(self, text: str, src: str, tgt: str) -> str:
        result = self.translate_with_stats(text, src, tgt)
        if result.capped:
            raise DegenerateTranslationError(
                f"generation hit the {result.cap}-token cap without finishing"
            )
        return result.text

    def translate_with_stats(self, text: str, src: str, tgt: str) -> TranslationResult:
        """Translate and report token counts and whether the output cap was hit (no exception).

        `translate` is the guarded entry point; the evaluation uses this one to measure the cap.
        """
        sentences = validate_request(text, src, tgt)
        if not sentences:
            return TranslationResult("", 0, 0, 0, capped=False)
        loaded = self.load()
        src_code = LANGUAGES[src].indictrans_code
        tgt_code = LANGUAGES[tgt].indictrans_code

        import torch

        with self._lock:
            batch = loaded.processor.preprocess_batch(
                sentences, src_lang=src_code, tgt_lang=tgt_code
            )
            inputs = loaded.tokenizer(
                batch,
                return_tensors="pt",
                padding="longest",
                truncation=True,
                max_length=self._max_length,
            ).to(loaded.device)
            longest_input = int(inputs["input_ids"].shape[1])
            cap = output_token_cap(longest_input, self._max_length)
            with torch.inference_mode():
                generated = loaded.model.generate(
                    **inputs,
                    num_beams=self._num_beams,
                    num_return_sequences=1,
                    max_new_tokens=cap,
                    use_cache=True,
                )
            # A finished row has an EOS after its first token (shorter rows are padded after it).
            # Column 0 is skipped because this model's decoder start token is also EOS (id 2).
            # No EOS means the cap cut the row off mid-loop.
            is_eos = generated[:, 1:] == loaded.tokenizer.eos_token_id
            finished = is_eos.any(dim=1)
            # Tokens generated per row, EOS included: the position of the first EOS, else all.
            row_lengths = torch.where(finished, is_eos.int().argmax(dim=1) + 1, is_eos.shape[1])
            decoded = loaded.tokenizer.batch_decode(
                generated, skip_special_tokens=True, clean_up_tokenization_spaces=True
            )
            translated: list[str] = loaded.processor.postprocess_batch(decoded, lang=tgt_code)
        return TranslationResult(
            text=" ".join(translated),
            longest_input_tokens=longest_input,
            longest_output_tokens=int(row_lengths.max()),
            cap=cap,
            capped=not bool(finished.all()),
        )
