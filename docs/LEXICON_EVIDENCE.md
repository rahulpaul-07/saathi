# Chip lexicons for ta, te, gu, ml, mr, pa: evidence

The first part covers Tamil and Telugu; "Round 2" at the end covers Gujarati, Malayalam, Marathi
and Punjabi.

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

# Round 2: Gujarati, Malayalam, Marathi and Punjabi (2026-10-30)

Same status and same method as above: **machine-verified, not native-reviewed.** Code:
`src/saathi/facts/lexicons_gu_ml_mr_pa.py`; one unit test per entry and four verbatim-transcript
tests: `tests/test_facts_gu_ml_mr_pa.py`. The STT wrote number words, never digits, in all four
languages, so without these tables a spoken gate, cross or floor produced no chip.

## How the evidence was made

1. The same 8 probe sentences per language (`scripts/probe_numbers.py --round2`), the words in
   `saathi.evaluation.lexprobe`. Evidence ids `p1`-`p8` are gu-probe-N, ml-probe-N and so on.
2. Back-translation with local indic-en (`--round2 --table`, no Gnani calls): 31 of 32 sentences
   kept all their numbers. One was flagged: **pa-probe-4** (the 16-20 block list), where 19 (ਉੱਨੀ)
   came back as "one". The spoken word was still written back by the STT, so the entry exists; the
   flag says the local translator may lose a Punjabi 19 on the rider's side.
3. TTS then STT for each sentence: 64 planned calls, limit 72, 70 spent (retries after Gnani 504s
   count). Transcripts: `eval/state/lexicon_probe_round2.json` (gitignored; synthetic number lists).
4. A script check confirmed every lexicon entry appears verbatim in a transcript, and the
   own-script test (Gujarati U+0A80-U+0AFF, Malayalam U+0D00-U+0D7F, Devanagari U+0900-U+097F,
   Gurmukhi U+0A00-U+0A7F) passes for all four.

## Where the STT wrote something other than what was spoken

| Lang | Spoken | Written (in the lexicon) |
|---|---|---|
| gu | flat | ફ્લૅટ and ફ્લેટ (both mapped); main મેઈન -> મેઇન |
| ml | 9 | ഒമ്പത് (cardinal), ഒൻപതാം (ordinal, probe) |
| ml | 19 | പത്തൊൻപത് (spoken പത്തൊമ്പത്) |
| mr | ordinal 11 | अकरावं (spoken अकरावा) |
| mr | ordinal 19 | एकोणीसावा (spoken एकोणिसावा) |
| pa | 9 | ਨੌ (spoken ਨੌਂ) |
| pa | 14, 16, 18 | ਚੌਦ੍ਹਾਂ, ਸੋਲ੍ਹਾਂ, ਅਠਾਰ੍ਹਾਂ (half-h) |
| pa | ordinals 11-14, 18 | half-h forms such as ਗਿਆਰ੍ਹਵਾਂ |
| pa | cross | ਕਰਾਸ and ਕ੍ਰਾਸ (both mapped) |

## Known gaps

- **Marathi landmarks are not covered.** The STT glued the cue to the name ("बेकरीसमोर"), and the
  extractor matches whole tokens, so there is no postposition to match. Marathi gets no landmark
  chip; the rider still gets the translated audio.
- **Punjabi ordinal 17 is absent.** The STT wrote the spoken ordinal as the cardinal ਸਤਾਰ੍ਹਾਂ, so 17
  has no ordinal entry; as a cardinal before a trigger it already reads as 17.
- **Malayalam "മീൻ" (fish) for "മെയിൻ"** once, for 15 (ml-probe-7). It is STT noise and is not mapped.
- Numbers above 20, digit ordinals, block and flat letters were not probed (as for ta and te).
- No noise testing; no native review.

## Held-out run (24 sentences, 48 calls)

The probe words are also the lexicon, so scoring the probe would be circular. A second set
(`saathi.evaluation.extragold`, `scripts/eval_facts_extra.py`) recombines the probe words in new
orders and number-trigger pairings, for all six round 1 and round 2 languages, 4 sentences each,
through TTS and STT again. Results are in docs/EVAL.md. It found five real gaps, all spellings the
STT wrote that the probe had not produced; they were then added to the lexicons, one test each
(`tests/test_extragold.py`):

| Lang | Added | Heard in | Why it was missing |
|---|---|---|---|
| ta | ordinal 13 பதின்மூன்றாவது | x-ta-3 | the probe had written பதிமூன்றாவது |
| te | ordinal 7 ఏడో | x-te-1 | the probe wrote only the -వ form for 6-10 |
| te | ordinal 9 తొమ్మిదో | x-te-2 | same |
| ml | ordinal 9 ഒമ്പതാം | x-ml-2 | the probe wrote ഒൻപതാം |
| pa | cardinal 12 ਬਾਰ੍ਹਾਂ | x-pa-1 | the probe wrote ਬਾਰਾਂ |

The lesson: one STT rendering per word is not the whole space. Each of these words has at least
two spellings, and the lexicons hold only the ones seen so far.
