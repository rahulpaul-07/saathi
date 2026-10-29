# Tamil and Telugu chip lexicons: evidence

Status of every entry: **machine-verified, not native-reviewed.** Nobody who reads Tamil or Telugu
has checked these words. Each one is a spelling that the real Gnani STT wrote when it heard
synthetic Gnani TTS speech. A word the STT never wrote is not in the lexicon even if it is standard
Tamil or Telugu, so a gap means "not heard". Code: `src/saathi/facts/lexicons_ta_te.py`; one unit
test per entry: `tests/test_facts_ta_te.py`.

## Why

Tamil and Telugu STT write spoken numbers as words ("மூன்று", "ఒకటి"), not digits. The universal
layer only reads digits and English direction words, so the demo clips ta-gate and te-gate gave no
chips on the rider screen (found with `scripts/transcribe_demo.py`, 2026-10-29).

## How the evidence was made

1. 8 probe sentences per language (`saathi.evaluation.lexprobe`) list the numbers 1-20 as cardinals
   (after gate, flat, floor, block) and as ordinals (before cross, floor, main), and end with a
   landmark cue (opposite, near, next to, behind) after the word for "bakery".
2. Each sentence was back-translated with local indic-en (`scripts/probe_numbers.py --table`): all
   16 kept their numbers. The Tamil cues came back loosely ("against the bakery", "Bakery Side").
3. Each sentence went through Gnani TTS, then STT (`scripts/probe_numbers.py`, 32 calls). The words
   below are what the STT wrote. Transcripts are kept locally in `eval/state/lexicon_probe.json`
   (gitignored); they are synthetic number lists, not addresses.
4. The two demo clips (ta-gate, te-gate) were transcribed again (`scripts/transcribe_demo.py`); both
   now give all four chips and the script exits 0.

Evidence ids: `p1`-`p8` are ta-probe-N or te-probe-N; `clip` is the demo clip; `recheck` is
`scripts/probe_numbers.py --ordinal5` (2 calls, 2026-10-29): the sentence "ஐந்தாவது கிராஸ்" was
spoken and the STT wrote the same two words back. ta-probe-5 had dropped it.

A script check (`test_every_entry_uses_only_its_own_script`) requires every lexicon entry to use
only code points of its own Unicode block (Tamil U+0B80-U+0BFF, Telugu U+0C00-U+0C7F) plus spaces.
No entry failed it; the one mixed-script spelling that was seen was a typo in a chat report.

## Numbers (cardinals)

| Value | Tamil | Evidence | Telugu | Evidence |
|---|---|---|---|---|
| 1 | ஒன்று | p1 | ఒకటి | p1, clip |
| 2 | இரண்டு | p1 | రెండు | p1 |
| 3 | மூன்று | p1, clip | మూడు | p1 |
| 4 | நான்கு | p1 | నాలుగు | p1, clip |
| 5 | ஐந்து | p1 | ఐదు | p1 |
| 6 | ஆறு | p2 | ఆరు | p2 |
| 7 | ஏழு | p2 | ఏడు | p2 |
| 8 | எட்டு | p2 | ఎనిమిది | p2 |
| 9 | ஒன்பது | p2 | తొమ్మిది | p2 |
| 10 | பத்து | p2 | పది | p2 |
| 11 | பதினொன்று | p3 | పదకొండు | p3 |
| 12 | பன்னிரெண்டு (spoken பன்னிரண்டு) | p3 | పన్నెండు | p3 |
| 13 | பதிமூன்று (spoken பதின்மூன்று) | p3 | పదమూడు | p3 |
| 14 | பதினான்கு | p3 | పద్నాలుగు | p3 |
| 15 | பதினைந்து | p3 | పదిహేను | p3 |
| 16 | பதினாறு | p4 | పదహారు | p4, p8 |
| 17 | பதினேழு | p4 | పదిహేడు | p4, p8 |
| 18 | பதினெட்டு | p4 | పద్దెనిమిది | p4 |
| 19 | பத்தொன்பது | p4 | పందొమ్మిది (spoken పంతొమ్మిది) | p4, p8 |
| 20 | இருபது | p4 | ఇరవై | p4, p8 |

## Ordinals

| Value | Tamil | Evidence | Telugu | Evidence |
|---|---|---|---|---|
| 1 | முதல் | p5 | మొదటి | p5 |
| 2 | இரண்டாவது | p5, clip | రెండో | p5, clip |
| 3 | மூன்றாவது | p5, clip | మూడో | p5 |
| 4 | நான்காவது | p5 | నాలుగో | p5 |
| 5 | ஐந்தாவது | recheck | ఐదో | p5 |
| 6 | ஆறாவது | p6 | ఆరవ | p6 |
| 7 | ஏழாவது | p6 | ఏడవ | p6 |
| 8 | எட்டாவது | p6 | ఎనిమిదవ | p6 |
| 9 | ஒன்பதாவது | p6 | తొమ్మిదవ | p6 |
| 10 | பத்தாவது | p6 | పదవ | p6 |
| 11 | பதினொன்றாவது | p7 | పదకొండో | p7 |
| 12 | பன்னிரெண்டாவது | p7 | పన్నెండో | p7 |
| 13 | பதிமூன்றாவது | p7 | పదమూడో | p7 |
| 14 | பதினான்காவது | p7 | పద్నాలుగో | p7 |
| 15 | பதினைந்தாவது | p7 | పదిహేనో | p7 |
| 16 | பதினாறாவது | p8 | none: written as the cardinal పదహారు | p8 |
| 17 | பதினேழாவது | p8 | none: written as the cardinal పదిహేడు | p8 |
| 18 | பதினெட்டாவது | p8 | పద్దెనిమిదో | p8 |
| 19 | பத்தொன்பதாவது | p8 | none: written as the cardinal పందొమ్మిది | p8 |
| 20 | இருபதாவது | p8 | none: written as the cardinal ఇరవై | p8 |

Telugu 6-10 were spoken as -వ forms and written that way; the -ో forms of 6-10 were not tested, so
they are not in the lexicon. The cardinals 16, 17, 19, 20 before a trigger already give the right
number ("పదహారు క్రాస్" is cross 16).

## Trigger words, fillers and landmark cues

| Role | Tamil | Evidence | Telugu | Evidence |
|---|---|---|---|---|
| gate | கேட் | p1, clip | గేట్ | p1, clip |
| cross | கிராஸ் | p5, p8, clip | క్రాస్ | p5, clip |
| main | மெயின் | p7, clip | మెయిన్ | p7, clip |
| floor | ஃப்ளோர், இப்ளோர், இப்லோர், இப்லோ | p6; p3 (three spellings) | ఫ్లోర్ | p3, p6 |
| block | பிளாக் | p4 | బ్లాక్ | p4 |
| flat | பிளாட் | p2 | ఫ్లాట్ | p2 |
| number filler | நம்பர் | p1-p4, clip | నంబర్, నెంబర్ | p1-p4, clip; p1, p3 |
| opposite | எதிரில் | p5, clip | ఎదురుగా | p5, clip |
| near | அருகில் | p6 | దగ్గర | p6 |
| next to | பக்கத்தில் | p7 | పక్కన | p7 |
| behind | பின்னால் | p8 | వెనుక | p8 |

The Tamil cues are confirmed as written by the STT in context (the back-translation alone was
loose for எதிரில் and பக்கத்தில்).

## Not covered, and why

- Numbers above 20: not probed. Only digits are read.
- Block and flat letters (Block C), digit ordinals ("2வது"), "number" before the value on the
  value-first side: not probed, so absent.
- Telugu "క్లాస్" appeared once for "cross" (te-probe-8). It is STT noise and is not mapped.
- Noise robustness: the probe is clean TTS to STT; only the two demo clips were tested with
  street noise (10 dB).
- A native speaker has not read any of this. The ta and te chip rules are machine-verified only,
  whatever the tier label of the language says.
