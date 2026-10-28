# Evaluation (slice 5)

Status: the translation evaluation is done. The Gnani-backed parts (clean synthetic audio, turn
latency, real-voice STT) have code and tests but have NOT been run; their sections below say
"pending". Raw numbers are in `eval/results/`; the generated tables are in
`eval/results/translation_summary.md` (and `stt_summary.md` once the Gnani steps run).

## Method

- Data: FLORES-200 devtest (1012 sentences, 4 languages), CC BY-SA 4.0, Meta AI (NLLB team).
  Downloaded by `scripts/fetch_flores.py`, pinned by SHA-256, kept out of git. The result files
  contain model outputs for FLORES inputs and carry the same license.
- Metric: chrF++ = sacrebleu 2.6.0 `CHRF(word_order=2)`, corpus level. The greedy-vs-beam gain is
  also reported per sentence with a paired bootstrap 95% CI (fixed seed).
- Sample: 50 evenly spaced devtest sentences for each of the 12 directed pairs, greedy vs
  5 beams. Greedy was also run on all 1012 sentences for the 4 app directions (bn->kn, kn->bn,
  hi->ta, ta->hi).
- Hardware and power: RTX 3050 6GB laptop GPU, fp16, torch 2.9.1+cu128, **AC power for every
  shard** (recorded per result file; the scripts refuse to run on battery and never mix states).
  The translator ran with 3 warm-up calls; timing is per sentence, one sentence at a time.
- Text normalization for STT scoring (NFC, punctuation replaced by a space, whitespace collapsed,
  case folded) is applied before CER, chrF++ and word matching. Translation chrF++ is computed on
  raw text, as is standard.
- The "clean synthetic audio" label: Gnani TTS audio fed to Gnani STT is Gnani's voice into
  Gnani's ears. It is an optimistic best case, not a measure of real users.

## Translation: greedy vs beam5 (AC power, 50 sentences per pair)

| | greedy | beam5 |
|---|---|---|
| app pairs, per-sentence chrF++ gain of beam5 | | +0.32 (95% CI -0.49 to +1.07, n=200) |
| mean ms per sentence added by beam5, app pairs | | +285 |
| runaway outputs (cap hit and repeated phrase) of 600 | 0 | 4 |

- bn->kn, the pair the app is mostly used for, is **worse** with beam5 (chrF++ 43.9 to 41.6) and
  slower (mean 809 to 1454 ms, p95 1748 to 4664 ms). Two of the four beam runaways are bn->kn.
- Across the 8 non-app pairs beam5 gains +0.66 (CI +0.22 to +1.09) for +84 ms. That is
  statistically visible but small, and those pairs are not in the product.
- Reading: on the app pairs the quality gain is not distinguishable from zero and costs about
  285 ms and a higher runaway rate. **Recommendation: keep greedy.** This rests on a 50-sentence
  sample; it is a decision with a wide interval, not a proven difference.
- Caveat on timing: the very first shard (greedy hi->bn, 1290 ms mean) is an outlier
  (probably CPU contention from my own test runs at the time; not verified) against its beam twin. Per-pair timing differences of a few
  hundred ms between shards should not be over-read; the pooled numbers are more reliable.

## Runaway guard and the 2x cap

- **False flags: none found.** The repeated-phrase guard flags 0 of 1012 human FLORES reference
  sentences in each of the four languages. Greedy flagged 0 of 600 on the 50-sentence sample.
- **But greedy does run away on the full devtest.** On all 1012 sentences, greedy bn->kn hit the
  token cap 15 times (1.5%), and kn->bn, hi->ta had none; ta->hi had one repeated-phrase output
  ("लगभग" four times) that finished normally. All 15 bn->kn outputs ran to the cap (ratio 2.1 to 2.3); 12 also contain a repeated phrase.
  I read only the first 100 characters of each, not every output in full
  (`eval/results/translation_summary.md` lists them). The 50-sentence sample showed 0 of 50 for greedy, so a small sample hides a
  1-2% failure rate. Expect the app to see this on roughly 1 in 70 bn->kn sentences; the guard
  turns each one into a coded 422 instead of a paid TTS call. Three of the 15 (#321, #503, #507)
  hit the cap without a repeated phrase: only the cap signal caught them, so the EOS check in
  `translate()` earns its place.
- Output/input token ratio of outputs that did NOT run away (greedy): max 1.21 (bn), 1.42 (hi),
  1.46 (kn on the sample), 1.50 (ta); on the full devtest the non-runaway kn outputs stay under
  1.5 too. Tamil, the language to watch, peaks at 1.50, against a cap of 2x + 10 tokens. The 2x
  cap therefore has about 33% headroom for real translations on this data and cuts only
  runaways (all of which show ratios of 2.1 to 2.3, because of the +10 slack).
- Open question: does beam5 fix bn->kn runaways on the full devtest, or make them worse? On 50
  sentences beam5 had 2 for bn->kn against greedy's 0. A full beam5 bn->kn pass (about 20 min,
  no Gnani) would settle it; it has not been run.

## Full devtest, greedy, app pairs (AC power)

| pair | chrF++ (1012) | chrF++ (50-sample) | ms p50 / p95 | flagged |
|---|---|---|---|---|
| bn->kn | 42.2 | 43.9 | 551 / 1200 | 15 |
| hi->ta | 47.9 | 46.7 | 500 / 881 | 0 |
| kn->bn | 41.2 | 41.1 | 447 / 805 | 0 |
| ta->hi | 43.6 | 43.0 | 457 / 831 | 1 |

The 50-sample scores sit within about 2 chrF++ of the full-devtest scores, which gives a feel
for the sampling noise. bn->kn on the full set includes the 15 runaways, which pull its score down.

Comparison with published IndicTrans2 FLORES numbers: **not completed.** Only a secondhand
snippet for Bengali averages (about 43.7 into bn and 41.6 out of bn for the distilled model) was
found; the paper's PDF could not be read here. Those are per-language averages over many
partner languages, not these pairs, so they only say my scores are in the right range. A proper
check needs the paper's per-pair table; open item.

## Phone cases (text only, AC power, `scripts/eval_phone_cases.py`)

| case | greedy | beam5 |
|---|---|---|
| 1: ground-truth text | correct, 29 tokens from 33 | correct, 30 from 33 |
| 1: as Gnani heard it ("সেই শর্ট ...") | **runaway** "ಆ ಚಿಕ್ಕ ಚಿಕ್ಕ ..." to the cap (76 tokens), caught by the guard | no loop, 27 tokens, but the first words are wrong ("ಆ ಶಾರ್ಟ್ ...") |
| 2: "আমার লাইফ তো পুরো বেকারই চলছে" | "ನಿರುದ್ಯೋಗಿ" (unemployed) | same |

Case 1 is an STT error amplified by greedy decoding, so beam5 avoided that loop on this input,
but one input is luck, not evidence (see the beam bn->kn result above). Case 2 is a word-sense
error in the translator that both modes share and the guard cannot see; it is a model limitation.
No recordings of either phone case exist, so no audio-level check was possible.

## STT, latency, start-of-clip: pending

Everything here needs Gnani calls and has not been run. The old FLORES-based plan
(`eval_turns.py`, 155-call cap) was replaced on 2026-10-29: the call plan and hard cap of 290 now
live in docs/DESIGN.md section 11, and the noise evaluation is `scripts/eval_noise.py` (see
docs/DECISIONS.md "Priority 2"). The latency study has no script yet. The list below is the old
plan's intent, kept until the new results replace it. Expected outputs, all labeled "clean
synthetic audio" where TTS-made:

- turn latency p50/p95 per stage for bn->kn, 40 measured turns (the first is a warm-up);
  with n=40 the p95 is close to the maximum;
- STT CER and chrF++ on normalized text, clean synthetic vs real speech on the same 10 sentences;
- first-2-word miss rate vs later-word miss rate (phone-mic clipping hypothesis), both sets;
- translation chrF++ from the STT transcript vs from the ground-truth text (STT vs translation
  error).

Known limits to state with the results: TTS audio is clean and cannot reproduce phone
microphone clipping, so a laptop-mic recording is also not the phone; 10 real clips is a small
set; the reader may deviate from the printed text, which counts as an STT error.

## How to record the real-speech set

Superseded by the gold-set recordings: see docs/recording/rahul_script.md (the old
`eval_turns.py sentences` / `stt-real` steps no longer exist).
