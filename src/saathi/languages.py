from dataclasses import dataclass
from typing import Literal

Tier = Literal["core", "reviewed", "beta"]


@dataclass(frozen=True)
class Language:
    name: str
    gnani_code: str  # BCP-47, used by Prisma STT and Timbre TTS
    indictrans_code: str  # FLORES-style code used by IndicTrans2
    tts_voice: str
    tier: Tier  # core: fully evaluated; reviewed: checked by a speaker; beta: path smoke-tested


# The 10 languages Gnani supports for both STT and TTS (docs.gnani.ai, checked 2026-10-11); Odia,
# Assamese and Urdu are in neither. Voices come from the Timbre v2.5 voice catalog.
LANGUAGES: dict[str, Language] = {
    "bn": Language("Bengali", "bn-IN", "ben_Beng", "Kirra", "core"),
    "en": Language("English", "en-IN", "eng_Latn", "Kaveri", "core"),
    "hi": Language("Hindi", "hi-IN", "hin_Deva", "Nalini", "core"),
    "kn": Language("Kannada", "kn-IN", "kan_Knda", "Saanvi", "core"),
    "te": Language("Telugu", "te-IN", "tel_Telu", "Suhana", "reviewed"),
    "gu": Language("Gujarati", "gu-IN", "guj_Gujr", "Falak", "beta"),
    "ml": Language("Malayalam", "ml-IN", "mal_Mlym", "Reshma", "beta"),
    "mr": Language("Marathi", "mr-IN", "mar_Deva", "Zahira", "beta"),
    "pa": Language("Punjabi", "pa-IN", "pan_Guru", "Mehuli", "beta"),
    "ta": Language("Tamil", "ta-IN", "tam_Taml", "Asmita", "beta"),
}

# The translation evaluation of docs/EVAL.md ran on these four languages and two pairs. The
# FLORES scripts stay pinned to them; the product itself accepts any pair in LANGUAGES.
EVALUATED_LANGUAGES: tuple[str, ...] = ("bn", "kn", "hi", "ta")
EVALUATED_PAIRS: frozenset[frozenset[str]] = frozenset(
    {frozenset({"bn", "kn"}), frozenset({"hi", "ta"})}
)
