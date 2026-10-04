from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    gnani_code: str  # BCP-47, used by Prisma STT and Timbre TTS
    indictrans_code: str  # FLORES-style code used by IndicTrans2
    tts_voice: str


# Voices come from the Timbre v2.5 voice catalog (docs.gnani.ai, TTS voices page).
LANGUAGES: dict[str, Language] = {
    "bn": Language("bn-IN", "ben_Beng", "Kirra"),
    "kn": Language("kn-IN", "kan_Knda", "Saanvi"),
    "hi": Language("hi-IN", "hin_Deva", "Nalini"),
    "ta": Language("ta-IN", "tam_Taml", "Asmita"),
}

SUPPORTED_PAIRS: frozenset[frozenset[str]] = frozenset(
    {frozenset({"bn", "kn"}), frozenset({"hi", "ta"})}
)
