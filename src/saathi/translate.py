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

# Break after sentence-final punctuation (including the Devanagari/Bengali danda).
_SENTENCE_BREAK = re.compile(r"(?<=[।.!?])\s+")


class TranslationInputError(ValueError):
    """The caller asked for something outside what the translator supports."""


class Translator(Protocol):
    def translate(self, text: str, src: str, tgt: str) -> str:
        """Translate `text` from language key `src` to `tgt` (keys from `LANGUAGES`)."""
        ...


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
        sentences = validate_request(text, src, tgt)
        if not sentences:
            return ""
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
            with torch.inference_mode():
                generated = loaded.model.generate(
                    **inputs,
                    num_beams=self._num_beams,
                    num_return_sequences=1,
                    max_length=self._max_length,
                    use_cache=True,
                )
            decoded = loaded.tokenizer.batch_decode(
                generated, skip_special_tokens=True, clean_up_tokenization_spaces=True
            )
            translated: list[str] = loaded.processor.postprocess_batch(decoded, lang=tgt_code)
        return " ".join(translated)
