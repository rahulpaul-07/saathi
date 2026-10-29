"""Tamil and Telugu extraction data, built from what Gnani STT wrote, not from the speaker's script.

Status of every entry: machine-verified, not native-reviewed. Each spelling below was produced by
the real STT in `scripts/probe_numbers.py` (TTS of a probe sentence, then STT) or in the demo clips
(`scripts/transcribe_demo.py`); the evidence per entry is in docs/LEXICON_EVIDENCE.md and the
sentences are in `saathi.evaluation.lexprobe`. A word the STT never wrote is absent even when it is
standard Tamil or Telugu, so a gap means "not heard", not "wrong". Numbers stop at 20, which is
what was probed; above 20 only digits are understood.

The STT wrote number words, never digits, for both languages: without this table a spoken gate,
cross or floor produces no chip at all.
"""

from saathi.facts.lexicon import Lexicon, phrases, same, trigger_map, words

REVIEW_STATUS = "machine-verified, not native-reviewed"


def _forms(spellings: dict[int, str]) -> dict[str, int]:
    """{value: "spelling another-spelling"} -> {normalized word: value}."""
    merged: dict[str, int] = {}
    for value, spec in spellings.items():
        merged |= same(spec, value)
    return merged


# --- Tamil ------------------------------------------------------------------------------------

# Heard in ta-probe-1..4 (and the ta-gate demo clip for 3). 12 and 13 were written பன்னிரெண்டு and
# பதிமூன்று, not the textbook பன்னிரண்டு and பதின்மூன்று that were spoken.
_TA_CARDINALS = {
    1: "ஒன்று", 2: "இரண்டு", 3: "மூன்று", 4: "நான்கு", 5: "ஐந்து",
    6: "ஆறு", 7: "ஏழு", 8: "எட்டு", 9: "ஒன்பது", 10: "பத்து",
    11: "பதினொன்று", 12: "பன்னிரெண்டு", 13: "பதிமூன்று", 14: "பதினான்கு", 15: "பதினைந்து",
    16: "பதினாறு", 17: "பதினேழு", 18: "பதினெட்டு", 19: "பத்தொன்பது", 20: "இருபது",
}  # fmt: skip

# Heard in ta-probe-5..8 and the ta-gate clip. The STT dropped "ஐந்தாவது கிராஸ்" from ta-probe-5;
# 5 comes from the two-call recheck (ta-ordinal-5), which wrote it.
_TA_ORDINALS = {
    1: "முதல்", 2: "இரண்டாவது", 3: "மூன்றாவது", 4: "நான்காவது", 5: "ஐந்தாவது",
    6: "ஆறாவது", 7: "ஏழாவது", 8: "எட்டாவது", 9: "ஒன்பதாவது", 10: "பத்தாவது",
    11: "பதினொன்றாவது", 12: "பன்னிரெண்டாவது", 13: "பதிமூன்றாவது", 14: "பதினான்காவது",
    15: "பதினைந்தாவது", 16: "பதினாறாவது", 17: "பதினேழாவது", 18: "பதினெட்டாவது",
    19: "பத்தொன்பதாவது", 20: "இருபதாவது",
}  # fmt: skip

TA = Lexicon(
    numbers=_forms(_TA_CARDINALS),
    ordinals=_forms(_TA_ORDINALS),
    hundred_words=frozenset(),
    hundred_joiners=frozenset(),
    spaced_tens=False,
    ordinal_suffix_tokens=frozenset(),
    digit_ordinal_suffixes=frozenset(),
    fillers=words("நம்பர்"),
    letters={},
    triggers=trigger_map(
        gate="கேட்",
        # The STT wrote the floor word four ways for one spoken word (ta-probe-3 and 6).
        floor="ஃப்ளோர் இப்ளோர் இப்லோர் இப்லோ",
        cross="கிராஸ்",
        main="மெயின்",
        block="பிளாக்",
        flat="பிளாட்",
    ),
    landmark_before=frozenset(),
    # Heard after "பேக்கரி" in ta-probe-5 (எதிரில், also the demo clip), 6, 7 and 8.
    landmark_after=phrases("எதிரில்|அருகில்|பக்கத்தில்|பின்னால்"),
    stopwords=frozenset(),
    leading_particles=frozenset(),
    trailing_particles=frozenset(),
)

# --- Telugu -----------------------------------------------------------------------------------

# Heard in te-probe-1..4 (and the te-gate clip for 1 and 4). 19 was written పందొమ్మిది, not the
# spoken పంతొమ్మిది.
_TE_CARDINALS = {
    1: "ఒకటి", 2: "రెండు", 3: "మూడు", 4: "నాలుగు", 5: "ఐదు",
    6: "ఆరు", 7: "ఏడు", 8: "ఎనిమిది", 9: "తొమ్మిది", 10: "పది",
    11: "పదకొండు", 12: "పన్నెండు", 13: "పదమూడు", 14: "పద్నాలుగు", 15: "పదిహేను",
    16: "పదహారు", 17: "పదిహేడు", 18: "పద్దెనిమిది", 19: "పందొమ్మిది", 20: "ఇరవై",
}  # fmt: skip

# Heard in te-probe-5..8 and the te-gate clip. 6-10 were spoken with -వ and written that way; the
# -ో forms of 16, 17, 19 and 20 came back as the cardinals above ("పదహారు క్రాస్"), so they are
# not ordinal entries: the cardinal reading already gives the right value before a trigger.
_TE_ORDINALS = {
    1: "మొదటి", 2: "రెండో", 3: "మూడో", 4: "నాలుగో", 5: "ఐదో",
    6: "ఆరవ", 7: "ఏడవ", 8: "ఎనిమిదవ", 9: "తొమ్మిదవ", 10: "పదవ",
    11: "పదకొండో", 12: "పన్నెండో", 13: "పదమూడో", 14: "పద్నాలుగో", 15: "పదిహేనో",
    18: "పద్దెనిమిదో",
}  # fmt: skip

TE = Lexicon(
    numbers=_forms(_TE_CARDINALS),
    ordinals=_forms(_TE_ORDINALS),
    hundred_words=frozenset(),
    hundred_joiners=frozenset(),
    spaced_tens=False,
    ordinal_suffix_tokens=frozenset(),
    digit_ordinal_suffixes=frozenset(),
    fillers=words("నంబర్ నెంబర్"),  # both written for one spoken word (te-probe-1 and 3)
    letters={},
    triggers=trigger_map(
        gate="గేట్",
        floor="ఫ్లోర్",
        cross="క్రాస్",
        main="మెయిన్",
        block="బ్లాక్",
        flat="ఫ్లాట్",
    ),
    landmark_before=frozenset(),
    # Heard after "బేకరీ" in te-probe-5 (ఎదురుగా, also the demo clip), 6, 7 and 8.
    landmark_after=phrases("ఎదురుగా|దగ్గర|పక్కన|వెనుక"),
    stopwords=frozenset(),
    leading_particles=frozenset(),
    trailing_particles=frozenset(),
)
