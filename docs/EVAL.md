# Evaluation (slice 5)

Status (2026-10-30): the translation evaluation, the noise evaluation on synthetic gold audio, STT
on real public speech (FLEURS), the fact extractor on all ten languages and the turn latency study
(bn to kn) are done. The start-of-clip split is still pending. Raw numbers
are in `eval/results/`; the generated tables are in `eval/results/translation_summary.md`,
`noise_summary_synth.md` and `speech_summary.md`.

> **Scorer note, 2026-11-01.** Every fact-recall number in this file and in the README is scored with
> the current extractor, which reads "Gate No. 2", "No. 2 cross" and "4 floors"; before that date
> the English layer missed them. The old values, kept for comparison only: masking A/B 0.674 plain,
> 0.747 masked, 0.843 with fallback (`eval/results/masking_ab.json`, which still holds the old
> scoring); matrix back-translation score 0.75 plain, 0.68 masked (`eval/results/translation_matrix.json`,
> old scoring). Re-scoring changed nothing else: the noise and speech summaries regenerate
> byte-identical and `facts_extra.json` is unchanged. The per-pair tables and the diagnosis in the
> matrix sections below keep the old scoring and are labelled where they appear; the new-scorer
> matrix totals are in "Conditional masking and the English scorer fix" at the end.

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

## Audio sources and labels

State this plainly wherever a number is quoted.

- **Address facts (gate, floor, cross/main, landmark): clean synthetic.** The 30 gold sentences,
  including every Kannada one, are spoken by Gnani TTS (`scripts/make_gold_tts.py`). No person
  was recorded for them. They measure the fact pipeline end to end on clean machine voices, with
  noise added by the harness; they say nothing about real speakers.
- **Real human speech: FLEURS.** 10 read-speech clips for each of bn, en, gu, hi, kn, ml, mr, pa,
  ta, te (100 clips), scored by character error rate, clean and with street noise at 20/10/5 dB.
  The clips are the first eligible ones (3 to 30 s, one per sentence id) in the dataset's archive
  order, not hand-picked; each converted WAV is pinned by SHA-256 in `eval/gold/fleurs_manifest.json`.
  The audio itself is gitignored. FLEURS sentences are Wikipedia-style text, not addresses.
- **Noise: one licensed street recording.** "College Street" by Calcuttan, Freesound sound 181026,
  CC BY 4.0, https://freesound.org/people/Calcuttan/sounds/181026/. Only the public lossy preview
  is used (originals need a login), pinned by SHA-256 in `scripts/fetch_noise.py`; it contains
  distant hawker voices. Seeded pink noise is a secondary condition, reported separately.
- **Demo clips:** Gnani TTS plus that street noise at 10 dB, so no person appears in the demo.

Attribution. FLEURS: Google, CC BY 4.0, https://huggingface.co/datasets/google/fleurs. Conneau,
A., Ma, M., Khanuja, S., Zhang, Y., Axelrod, V., Dalmia, S., Riesa, J., Rivera, C., Bapna, A.
(2022). FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech.
arXiv:2205.12446. Clips were converted from 32-bit float to 16-bit PCM; nothing else was changed.

## Noise: address facts on synthetic gold audio (run 2026-10-30)

**Audio: synthetic. Gnani TTS speech (30 gold sentences, `scripts/make_gold_tts.py`, 30 calls) fed
to Gnani STT. No person was recorded.** This is Gnani's voice into Gnani's ears, an optimistic
best case, so the "clean" row is a ceiling and says nothing about real speakers.

Method (`scripts/eval_noise.py`, 150 calls, seed 20261029): each clip is scored clean and with the
Calcuttan street recording mixed in at 20, 10 and 5 dB SNR (pink noise at 10 dB as a secondary
condition). The STT transcript goes through the fact extractor and is compared with the gold facts.
Precision is the share of chips shown that are right; recall is the share of gold facts found; "all
facts right" is the share of utterances where every gold fact was found and none was wrong. Intervals
are 95% bootstrap CIs over utterances. Results: `eval/results/noise_stt_synth.json`, tables in
`eval/results/noise_summary_synth.md`. Test split n=20 (the headline), dev split n=10.

Test split, street noise (n=20):

| condition | precision | recall | all facts right | recall drop vs clean |
|---|---|---|---|---|
| clean | 0.91 [0.85, 0.97] | 0.84 [0.76, 0.92] | 0.55 [0.30, 0.75] | - |
| street 20 dB | 0.93 [0.87, 0.97] | 0.86 [0.77, 0.93] | 0.60 [0.40, 0.80] | -0.01 [-0.04, 0.00] |
| street 10 dB | 0.89 [0.82, 0.96] | 0.78 [0.68, 0.88] | 0.45 [0.25, 0.65] | 0.07 [-0.01, 0.15] |
| street 5 dB | 0.84 [0.74, 0.93] | 0.64 [0.51, 0.78] | 0.30 [0.10, 0.50] | 0.20 [0.09, 0.31] |
| pink 10 dB | 0.89 [0.82, 0.95] | 0.76 [0.65, 0.86] | 0.40 [0.20, 0.60] | 0.08 [0.00, 0.17] |

What it shows, and what it does not:

- Noise at 20 dB costs nothing measurable; at 10 dB the recall drop is small and its interval
  includes zero; at 5 dB (loud street) recall falls by 0.20 (CI 0.09 to 0.31).
- Even clean, only 55% of utterances have every fact right (CI 0.30 to 0.75). The misses are
  more often missing chips than wrong ones (precision, 0.84 or above, is higher than recall); this
  is read from the two aggregates, not from a per-fact error analysis. A missing chip is the safer
  failure (the card shows what it has and the rider asks).
- With n=20 the intervals are wide; differences of a few points between conditions are not
  resolved. The dev split (n=10) gives the same picture and is in the summary file.
- One street recording and one seeded pink noise; nothing about phone microphones, 8 kHz audio or
  wind.
- Gold sentences were written by the author, and "all facts right" depends on the extractor's rules
  per language (see docs/LEXICON_EVIDENCE.md). The pooled numbers are not broken down by language
  here.

## STT on real speech: FLEURS (run 2026-10-30)

**Audio: real human read speech (FLEURS test clips, CC BY 4.0).** 10 clips per language, 10
languages, 100 clips. These are Wikipedia-style sentences, not addresses, so this measures how well
Gnani STT hears these languages and these conditions, not the fact pipeline. Metric: character error
rate on normalized text (lower is better). `scripts/eval_speech.py`, 404 calls (400 planned plus 4
retries after 504 responses); resumed over several runs because Gnani returned 504 on some calls,
finished clips were kept. Results: `eval/results/speech_stt.json`, `eval/results/speech_summary.md`.

Mean CER by language, 95% bootstrap CI over clips (n=10 each):

| language | clean | street 20 dB | street 10 dB | street 5 dB |
|---|---|---|---|---|
| bn | 0.023 [0.011, 0.038] | 0.026 | 0.028 | 0.037 |
| en | 0.182 [0.043, 0.399] | 0.157 | 0.058 | 0.427 [0.196, 0.670] |
| gu | 0.068 [0.027, 0.118] | 0.069 | 0.071 | 0.075 |
| hi | 0.033 [0.018, 0.049] | 0.032 | 0.041 | 0.038 |
| kn | 0.044 [0.014, 0.084] | 0.045 | 0.049 | 0.051 |
| ml | 0.074 [0.045, 0.105] | 0.069 | 0.079 | 0.087 |
| mr | 0.032 [0.016, 0.055] | 0.034 | 0.033 | 0.033 |
| pa | 0.031 [0.025, 0.036] | 0.029 | 0.032 | 0.043 |
| ta | 0.055 [0.036, 0.076] | 0.056 | 0.065 | 0.088 |
| te | 0.125 [0.013, 0.332] | 0.129 | 0.129 | 0.130 |
| all (n=100) | 0.067 [0.043, 0.097] | 0.065 | 0.058 | 0.101 [0.064, 0.141] |

Paired CER increase over clean, pooled over all 100 clips: street 20 dB -0.002 [-0.009, 0.002];
street 10 dB -0.008 [-0.035, 0.006]; street 5 dB +0.034 [0.010, 0.062]. Only the 5 dB condition is
distinguishable from clean.

Caveats:

- n=10 per language: the per-language intervals are wide and a single clip can move a mean. The
  English row (CER 0.18 clean, 0.43 at 5 dB, CI up to 0.67) and Telugu (0.125 with a CI from 0.01 to
  0.33) are each driven by one or two clips, so they are not evidence that those languages are
  worse than the rest. They are the rows to re-run with more clips before drawing a conclusion.
- The clips are the first eligible ones in archive order, one per sentence id, read by a small number
  of speakers. Not a sample of delivery customers.
- The mixed-in street noise is the same recording for every clip.
- "All" is a pooled mean over clips; languages are weighted equally only because n is equal.
- The street 10 dB mean being below clean is noise in the estimate (the paired interval includes
  zero), not an improvement.

## Fact extraction on ta, te, gu, ml, mr, pa (held-out synthetic speech, run 2026-10-30)

The main gold set has only en, kn, hi and bn. For the other six a separate set of 24 sentences
(4 per language, `saathi.evaluation.extragold`) was spoken with Gnani TTS and read back with Gnani
STT (48 calls, plus retries after 504s), then scored with the same extractor
(`scripts/eval_facts_extra.py`, `eval/results/facts_extra.json`).

| Lang | n | all facts right | recall | precision |
|---|---|---|---|---|
| ta | 4 | 3 | 0.92 | 1.00 |
| te | 4 | 2 | 0.83 | 1.00 |
| gu | 4 | 4 | 1.00 | 1.00 |
| ml | 4 | 3 | 0.92 | 1.00 |
| mr | 4 | 4 | 1.00 | 1.00 |
| pa | 4 | 3 | 0.92 | 1.00 |
| all six | 24 | 19 | 0.93 (67 of 72 facts) | 1.00 |

These are the scores of the first run, before any lexicon change. All five misses were spelling
gaps: the STT wrote a valid variant the probe had not produced (ta ordinal 13, te ordinals 7 and 9,
ml ordinal 9, pa cardinal 12; see docs/LEXICON_EVIDENCE.md). Those spellings were then added, one
test each, and the same transcripts now score 24 of 24 with recall 1.00. That second number is NOT
a held-out result: the set was used to fix the lexicons, so it only shows the fixes work. A new
held-out set would be needed to measure the next round.

Caveats:

- 4 sentences per language is a very small n; 0.92 versus 1.00 is one fact. Read it as "no
  language is broken", not as a ranking.
- The sentences recombine words the lexicon probe already spoke (new orders and number-trigger
  pairings). It tests composition and spelling variants, not unseen vocabulary.
- Synthetic Gnani TTS, one voice per language, clean audio, no noise. No landmark facts (the
  gold string for a free-text span needs a native reader), so landmarks are not scored here;
  Marathi has no landmark cues at all (docs/LEXICON_EVIDENCE.md).
- Precision of 1.00 means nothing wrong was asserted on these sentences, not that the extractor
  never asserts a wrong chip.
- All lexicons for these six languages are machine-verified, not native-reviewed.

## Turn latency, bn to kn (AC power, run 2026-11-01)

`scripts/latency_study.py --yes`: 20 turns of STT (Gnani), local IndicTrans2 translation and TTS
(Gnani), 40 calls, `eval/results/latency.json`. Source audio: 4 synthetic Gnani TTS clips of
Bengali gold sentences cycled over the turns. All 20 turns completed with no retries or failures.

| Stage | p50 | p95 | max |
|---|---|---|---|
| STT (Gnani) | 0.9 s | 1.1 s | 1.4 s |
| Translate (local) | 0.9 s | 1.8 s | 13.5 s |
| TTS (Gnani) | 1.1 s | 1.3 s | 1.3 s |
| Total | 2.9 s | 4.0 s | 16.2 s |

Superseded run, 2026-10-30 (AC power, n=19, during a stretch of Gnani 504s): p50 4.2 s, p95 11.3 s.
That tail measured the bad service stretch, not typical use.

Caveats:

- n=20: the p95 is close to the second-largest value, so quote the p50 and say the tail is long.
- One translation took 13.5 s (the max); the cause was not investigated, so the total max of 16.2 s
  is a single outlier, not a pattern.
- Synthetic, clean, short clips from one voice: real phone audio is longer and noisier, and
  longer clips take longer to transcribe.
- One pair, one machine (the author's laptop), the translator already loaded. A cold start adds
  the model load time, which is not measured here.
- The pair is an example; roles are independent of languages and other pairs were not measured.

## STT output format: verbatim vs transcribe (3 real calls plus 1 failed, run 2026-11-03)

Saathi sends no `format` field, so Gnani's default (verbatim: numbers spelled as words) applies.
A one-off probe sent `format=transcribe` (inverse text normalization) for one Gnani TTS clip per
language, same endpoint and default model, and compared it with the stored bundle transcript of
the same clip. The Tamil request first returned an HTTP 504 and was sent again later; the ledger
counted all 4 attempts. The probe script and its raw output were throwaway files and are not in the repo.

| Clip | Verbatim | transcribe | Facts, both |
|---|---|---|---|
| kn-gate-correction | ... ನಂಬರ್ ಎರಡು | ... ನಂಬರ್ 2 | gate=2 |
| ta-gate | இரண்டாவது ... மூன்று | 2nd ... 3rd ... 3 | cross=2, main=3, gate=3, landmark |
| te-gate | రెండో క్రాస్ నాలుగు ... ఒకటి | రెండో క్రాస్ 4 ... 1 | cross=2, main=4, gate=1, landmark |

- Digits came back for all three languages (Tamil ordinals as "2nd", "3rd"; the Telugu ordinal
  stayed a word). Saathi's extractor found identical facts from both outputs on every clip.
- n=3 short synthetic clips, one per language: it shows the option works on these clips, not how
  accurate it is. Saathi was not changed to use it, since number words already work.

## Not run tonight

- Start-of-clip split (first-2-word miss rate): needs the real-speech set; not run.

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

## Masking A/B (slice 5, text only, `scripts/eval_masking.py`)

All 90 gold turns (30 synthetic utterances x 3 target languages), real IndicTrans2, greedy,
`eval/results/masking_modes.json` (arms A_plain, B_current, C_current, scorer "new"; rerun 2026-11-01 with the fixed extractor; `masking_ab.json` holds the earlier scoring). A fact counts as recalled when its class and value appear in the
text the listener would get. No STT or TTS is involved, and the gold text is ours, not recorded
speech, so these numbers are optimistic about the front half of the pipeline.

| arm | what it is | fact recall | wrong extras | all facts correct | loanwords kept |
|---|---|---|---|---|---|
| A | toolkit default: translate the raw sentence | 0.701 | 66 | 11/90 | 128/255 |
| B | masked: numbers and address words become placeholders, restored in plain digits and the listener's script | 0.759 | 65 | 13/90 | 153/255 |
| C | B plus the fallback: if a placeholder is lost or invented, speak the templated fact summary | 0.854 | 60 | 21/90 | 166/255 |

- Old scoring of this table (pre-2026-11-01 extractor): A 0.674, B 0.747, C 0.843; the 2026-11-01 rerun
  scored with that extractor gives A 0.674, B 0.755, C 0.851 (see the last section).
- Correction, 2026-10-31 (figures in this bullet use the old scoring): this table was regenerated from a rerun of the script on current code
  (`eval/results/masking_ab.json`). The first recorded run, in commit 8e2d64d, showed B 0.808 with
  4/90 failed checks and C 0.851. It did not reproduce on current code or on the 8e2d64d sources
  (B 0.747, 9 to 10 of 90 failed; C 0.843 current, 0.851 on 8e2d64d). Cause unknown. A is
  unchanged at 0.674. The old file is in git history at 8e2d64d.
- Masking adds about 7 points of recall and the summary fallback about 10 more. Most turns still
  lose at least one fact in the translated text, and 9 of 90 masked translations failed the
  placeholder check. Masking is a modest improvement on this speech-style text, not a fix; the
  fallback and the chips are what keep the rider from acting on a wrong number.
- Chips are a second safety layer. They are extracted from the source transcript, not from the
  translation, so they do not depend on any arm above: a wrong translation still shows correct
  chips next to it. Arm recall measures the sentence the listener hears, not the chips.
- Landmark names in the listener's language passed the `plausible` rule 72 of 72 times. That rule
  catches runaway output, not wrong-but-fluent output, and no human has reviewed the renderings.

## Start-of-clip: pending

The noise evaluation, FLEURS CER, held-out facts and latency runs above replaced most of this plan.
Only the start-of-clip split has not been run. The old
FLORES-based plan
(`eval_turns.py`, 155-call cap) was replaced on 2026-10-29: the call plan and hard cap of 290 now
live in docs/DESIGN.md section 11, and the noise evaluation is `scripts/eval_noise.py` (see
docs/DECISIONS.md "Priority 2"). The latency study script exists (`scripts/latency_study.py`, dry-run
only so far). The list below is the old
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

Superseded: no one is recorded for this project (see "Audio sources and labels" below).
Recording scripts were removed on 2026-11-01. The old `eval_turns.py sentences` / `stt-real` steps no longer exist.

## Load test (fake Gnani)

`uv run --no-sync python scripts/load_rooms.py [--rooms N] [--turns N] [--gnani-ms MS]`. The app runs
in one process behind httpx's ASGI transport, with a fake Gnani client (40 ms per call, two calls
per turn) and a fake translator. No credits, no network, no GPU. Every room is a customer (en) and
a rider (kn) taking turns, two thirds spoken by the customer, with both event queues drained after
each turn. Per-IP rate limits are raised because one client drives all rooms.

| Run | Requests | Errors | Server time p50 | p95 | max | Wall |
|---|---|---|---|---|---|---|
| 1 room, 6 turns | 6 | 0 | 5.2 ms | 19.3 ms | 19.3 ms | 0.6 s |
| 50 rooms, 6 turns each | 300 | 0 | 41 ms | 75 ms | 127 ms | 1.1 s |
| 50 rooms, 60 turns each | 3000 | 0 | 39 ms | 85 ms | 129 ms | 11.1 s |

Process memory (working set): 69 MB before; 82 MB with 50 rooms of 6 turns alive; 84 MB with 50
rooms of 60 turns alive; unchanged after the rooms were closed.

Rerun on 2026-10-30 on AC power, after the rate-limiter sweep change. The earlier run (on
battery) gave p50 57 ms and 96 ms for the two 50-room rows and 16.1 s wall for 3000 turns; the
difference is mostly power state and background load, so do not read it as a speed-up from the
code change.

How to read this:

- "Server time" is the turn request's wall time minus the time spent in the fake Gnani calls. At 50
  rooms it is mostly queueing: all turns share one event loop and one core, so a turn waits for the
  others' CPU work (about 4 to 5 ms each, matching the single-room figure). It is the app's own
  overhead under 50-way concurrency, not a latency a user would see; a real turn is dominated by
  Gnani and the translation model (see the latency tables above).
- Not measured: the translation model, real Gnani latency and its rate limits, TLS, the network,
  SSE delivery to real browsers (the queues are drained in process), and more than one process.
- Memory did not grow with turns per room (81 MB at 6 turns, 84 MB at 60), consistent with the
  cap of 5 stored audio clips per room and a card that holds one entry per kind. It also did not
  fall after the rooms were closed, which is the Python allocator keeping freed memory, not
  evidence of a leak or of its absence; a long soak test would be needed to say more.
- Machine: Intel Core i7-13650HX (20 logical processors), Windows 11, **on AC power**
  (`read_power_state` reported `ac` just before the runs), other applications open. Run once per
  row, no warm-up, no repeats: treat the figures as rough.

## Translation-safety matrix, 10 x 10 (local model, no Gnani, run 2026-10-30 to 31)

Scoring note: the per-pair tables and averages in this section and in the diagnosis below use the
extractor from before 2026-11-01 (plain 0.75, masked 0.68 averaged over pairs). With the current
extractor the same 90 pairs score back 0.796 plain, 0.784 masked, direct 0.374 plain, 0.445 masked;
see the last section. Per-pair figures were not recomputed.

`scripts/eval_translation_matrix.py`, results in `eval/results/translation_matrix.json`. For each of
the 90 ordered pairs X to Y: the gold sentence in English is machine-translated to X (the source
text), translated X to Y two ways (plain, and masked as the app does), back-translated Y to English,
and the English extractor is scored against the gold facts. Recall only, landmarks excluded.

Caveats, all of which matter:
- The source text is machine-generated, not what a person would say. 12 of the 30 gold sentences are
  English as written; the other 18 were machine-translated to English first.
- Only the 20 "scorable" sentences are used (English text still scores full recall), 19 facts per
  sentence at most; each cell is 20 sentences, so one cell moves by about 0.03 per fact. Read the
  row and column averages, not single cells.
- The score includes the back-translation's own errors, so it is a floor on the X to Y quality. The
  en target has no back-translation step, which is why en columns tend to be higher.
- A digit written as a word counts as lost for the digit-survival figures in the JSON.
- Fallback rate is the share of masked translations where a slot was lost; the app would then speak
  the fact summary, which this matrix does not score.

Fact recall, plain (rows = source, columns = target):

| src \ tgt | bn | en | gu | hi | kn | ml | mr | pa | ta | te |
|---|---|---|---|---|---|---|---|---|---|---|
| bn | - | 0.72 | 0.65 | 0.63 | 0.63 | 0.68 | 0.58 | 0.67 | 0.61 | 0.65 |
| en | 0.72 | - | 0.82 | 0.84 | 0.86 | 0.79 | 0.65 | 0.89 | 0.77 | 0.82 |
| gu | 0.74 | 0.82 | - | 0.79 | 0.79 | 0.74 | 0.68 | 0.79 | 0.79 | 0.77 |
| hi | 0.75 | 0.84 | 0.86 | - | 0.88 | 0.86 | 0.77 | 0.89 | 0.72 | 0.77 |
| kn | 0.75 | 0.86 | 0.77 | 0.81 | - | 0.75 | 0.68 | 0.81 | 0.75 | 0.79 |
| ml | 0.68 | 0.79 | 0.67 | 0.72 | 0.68 | - | 0.61 | 0.75 | 0.67 | 0.74 |
| mr | 0.65 | 0.65 | 0.70 | 0.70 | 0.72 | 0.70 | - | 0.72 | 0.68 | 0.67 |
| pa | 0.63 | 0.89 | 0.84 | 0.84 | 0.86 | 0.81 | 0.77 | - | 0.72 | 0.77 |
| ta | 0.68 | 0.77 | 0.74 | 0.70 | 0.79 | 0.67 | 0.70 | 0.72 | - | 0.82 |
| te | 0.77 | 0.82 | 0.72 | 0.74 | 0.81 | 0.75 | 0.70 | 0.81 | 0.74 | - |

Fact recall, masked:

| src \ tgt | bn | en | gu | hi | kn | ml | mr | pa | ta | te |
|---|---|---|---|---|---|---|---|---|---|---|
| bn | - | 0.70 | 0.58 | 0.47 | 0.58 | 0.58 | 0.46 | 0.56 | 0.60 | 0.61 |
| en | 0.60 | - | 0.63 | 0.63 | 0.70 | 0.77 | 0.67 | 0.63 | 0.72 | 0.77 |
| gu | 0.61 | 0.84 | - | 0.58 | 0.68 | 0.67 | 0.65 | 0.72 | 0.70 | 0.70 |
| hi | 0.32 | 0.86 | 0.58 | - | 0.70 | 0.56 | 0.58 | 0.67 | 0.68 | 0.70 |
| kn | 0.49 | 0.82 | 0.75 | 0.63 | - | 0.77 | 0.68 | 0.70 | 0.77 | 0.75 |
| ml | 0.70 | 0.77 | 0.67 | 0.65 | 0.70 | - | 0.63 | 0.67 | 0.70 | 0.74 |
| mr | 0.56 | 0.65 | 0.68 | 0.65 | 0.70 | 0.58 | - | 0.67 | 0.67 | 0.60 |
| pa | 0.61 | 0.82 | 0.72 | 0.68 | 0.75 | 0.72 | 0.65 | - | 0.67 | 0.72 |
| ta | 0.77 | 0.82 | 0.79 | 0.70 | 0.82 | 0.74 | 0.74 | 0.79 | - | 0.79 |
| te | 0.60 | 0.79 | 0.68 | 0.61 | 0.68 | 0.65 | 0.60 | 0.67 | 0.68 | - |

Averages over the 90 pairs (mean of the ten per-source figures): plain 0.75, masked 0.68. By
source, plain ranges 0.65 (bn) to 0.82 (hi), masked 0.57 (bn) to 0.77 (ta). By target, plain
ranges 0.68 (mr) to 0.80 (en), masked 0.58 (bn) to 0.79 (en). Masked fallback rate per source is
0.01 to 0.09 (highest kn 0.09, hi 0.08); per target 0.01 to 0.11 (highest bn 0.11, ml 0.08).

What this says, and does not:
- On this test masking did NOT help: masked recall is below plain in most cells, the opposite of
  the text-only masking A/B above (0.674 to 0.747 after the correction). See the diagnosis below; the candidates I
  listed before diagnosing were: (1) the matrix back-translates the masked output, so placeholder or restored-slot
  wording may be hurt by the second translation, while the A/B scored the first translation;
  (2) the source here is machine-translated text where extraction for the source language finds
  fewer slots to mask (masking then only adds risk); (3) hi to bn (0.32 masked, 0.75 plain) and
  kn to bn (0.49) point at one bad pair rather than a general effect. Do not quote either arm as
  the app's real accuracy; the two experiments measure different things.
- The chips never depend on this path (they come from the speaker's own transcript), so these
  numbers bound the audio only.
- Marathi is the weakest target for plain translation and Bengali the weakest source.

### Why masking lost in the matrix: diagnosis (text only, no Gnani, 2026-10-31)

All figures in this diagnosis use the pre-2026-11-01 extractor, which is the cause it found; with the
current extractor the back-route gap between plain and masked is 0.012, not 0.07.

`scripts/analyze_masking_reversal.py` (`collect`, `report`, `examples`), summary in
`eval/results/masking_reversal.json`, per-sentence checkpoint in `eval/state/` (gitignored).
Coverage is complete: all 90 pairs, 20 sentences each (finished on AC power on 2026-10-31; the
first run covered 46 pairs and was stopped by the power guard, and the numbers below replace the
earlier partial figures). Nothing below was changed in the app. Synthetic
addresses only.

Hypothesis tested first: the matrix source is machine-translated, so numbers are digits, unlike the
number words STT returns, and masking only helps number words. Not supported:

| source | clear numbers | ascii digits | words | loanwords per sentence |
|---|---|---|---|---|
| bn | 29 | 0.52 | 0.48 | 1.0 |
| en | 57 | 0.46 | 0.54 | 3.1 |
| gu | 13 | 0.46 | 0.54 | 1.3 |
| hi | 40 | 0.35 | 0.65 | 1.6 |
| kn | 25 | 0.48 | 0.52 | 1.1 |
| ml | 17 | 0.65 | 0.35 | 1.4 |
| mr | 11 | 0.64 | 0.36 | 1.0 |
| pa | 22 | 0.50 | 0.50 | 1.6 |
| ta | 6 | 1.00 | 0.00 | 0.6 |
| te | 15 | 0.53 | 0.47 | 1.2 |

Apart from Tamil (6 numbers, all digits) the sources are about half digits and half words, and no source writes native-script digits. Recall
by how the sentence writes its numbers (non-en targets, "back" = the matrix score, "direct" = the
target-language extractor on the translated text, the A/B style of scoring):

| class | back plain | back masked | direct plain | direct masked |
|---|---|---|---|---|
| digits | 0.85 | 0.80 | 0.53 | 0.56 |
| words | 0.66 | 0.48 | 0.29 | 0.41 |
| mixed | 0.90 | 0.79 | 0.50 | 0.67 |
| no numbers | 0.65 | 0.66 | 0.23 | 0.24 |

Masking hurts the back-translated score in every class that has numbers, and hurts word sentences
most (so the hypothesis points the wrong way). On the direct score masking helps most for words
(+0.12) and mixed (+0.17), little for digits (+0.03) and not at all for sentences without numbers.
Target en has no back-translation and is neutral (plain 0.80, masked 0.79). Over all 90 pairs: back
plain 0.75 vs masked 0.68; direct plain 0.37 vs masked 0.44 (non-en targets only: back 0.74 vs
0.67, direct 0.32 vs 0.40). So the reversal is mostly a difference between two scoring routes, not
between two kinds of source text.

Where the masked loss comes from (facts masked lost beyond plain: 527; facts masked found that
plain missed: 170; net -357), by the first cause that applies:
- 257: the masked text itself lacks the fact by the target-language extractor.
- 162: the masked text is fine, but the back-translation lost it.
- 81: fallback, a placeholder was dropped (verified false; the app would speak the summary).
- 13: verified true, but the source digit is absent.
- 11: verified true, but placeholder residue (`<ID4]`, "I. D. 3") is left in the text.
- 3: the masked translation failed.

Fallback rate per source: bn 0.03, en 0.01, gu 0.02, hi 0.03, kn 0.07, ml 0.01, mr 0.07, pa 0.06,
ta 0.02, te 0.03. So fallbacks and corrupted placeholders explain about 92 of 527 lost facts; most
of the loss is verified, well-formed output.

By fact kind (masked lost while plain found / the reverse): gate 165 / 61, floor 147 / 19,
cross 126 / 18, main 79 / 22, flat 49 / 68, block 14 / 35. Flat and block numbers are the only
kinds where masking is net positive. The ordinal kinds lose most. In the examples the restore writes a bare
digit, so "fourth floor" becomes "4 floors" (bn "4 মেঝে", gu "2 ફ્લોર"), "second cross" becomes
"2 crosses", and the back-translation reads a quantity, not an ordinal.

Scoring fairness (5 sentences read by hand): in 3 of 5 the masked translation held every gold fact
and the loss was in the back-translation plus a strict scorer; in the other 2 the masked text
really lost the fact (a bare "2 crosses", and placeholder residue). The English extractor does not read
"Gate No. 2", "Cross No. 2" or "4 Floors" as the gold facts, while the plain back-translation
happened to write "second", "4th". So part of the matrix gap is the English extractor's coverage,
not translation quality. That is a limit of the metric, not proof that masked output is fine.
Concrete examples (source, plain, masked, lost fact) are in the tool output of `examples`.

The earlier gold-turn A/B does not reproduce. Re-run unchanged on the current code and on the
8e2d64d sources (the A/B-time code): A 0.674 (same), B 0.747 (not 0.808), C 0.851 / 0.843
(first recorded 0.851), masked verification failures 10 of 90 (9 on current code), not 4 of 90. The
masking code, loanword table and translator are unchanged between those revisions apart from the
digit fold, and the slot counts probed are identical. The cause of the 0.808 / 4 of 90 figures is
unknown (an earlier file state or nondeterminism are the candidates). The rerun makes the A/B
gain 7 points (0.674 to 0.747), not 13. `eval/results/masking_ab.json`, the README and the table
above now carry the current-code rerun; the first recorded file is in commit 8e2d64d.

Cause, as far as the evidence goes: masking replaces ordinal words and numbers with a bare digit,
which the second translation reads as a quantity; the strict English extractor then misses it; a
smaller share is placeholder corruption by the toolkit's entity wrapper (verified can still be true
with residue left). Still unknown: the 0.808 figure; whether a listener
would understand "2 crosses" in context; and how real STT number words behave (no recorded speech
in this test).

Proposal, not built: conditional masking. Mask cardinal values (flat, gate, block numbers) and
loanwords, where masking is net positive. Leave ordinal-bearing kinds (floor, cross, main) as the
translator writes them, or restore them with an ordinal marker in the target language. Also give
the English extractor "No. 2" and "4 Floors" forms so the metric stops penalising them. Digits
need not be treated differently from words: the digit/word split showed no effect. Any change
should be re-measured on the full 90 pairs and on the gold-turn A/B before it ships.

## Conditional masking and the English scorer fix (text only, no Gnani, 2026-11-01)

Two changes, measured separately so a number can be attributed to the right one.

1. **The English extractor** now reads "Gate No. 2" / "No. 2 cross" (a full stop after `no`, `nos`,
   `nr`, `num` no longer ends the phrase) and "4 floors" (`floors`, `storeys`). This is the scorer
   used on the English target of the A/B and for the back-translation score of the matrix. It also
   runs in the app for English speakers, which is the point of the fix.
2. **`SAATHI_MASKING_MODE=conditional`** (default `current`, unchanged). Cardinal kinds (gate, flat,
   block) and loanwords are masked as before. For the ordinal kinds (floor, cross, main) the number is
   masked and restored as the target language's ordinal word taken from the lexicon, or left
   unmasked where the lexicon has no such word. Bengali is deliberately excluded from ordinal
   restore (the lexicon spellings are normalised keys, not display text), so bn ordinals stay
   unmasked. Known limits: ordinal gender and case agreement is not handled (the first lexicon
   variant is used, e.g. Hindi masculine), values left unmasked are not covered by the slot check,
   and the extractor reads a spelled "fifty fifth" as 5.

`legacy` below is the same stored output scored with the extractor as it was before 2026-11-01
(`scripts/legacy_extractor.py`); `new` is the current one. Re-scoring changed no other published
result: the noise and speech summaries regenerate byte-identical, `facts_extra.json` and
`phone_cases.json` are unchanged, and the gold-set dev text score is unchanged (R=0.94, P=1.00).

### Gold-turn A/B, 90 turns (targets bn, hi, kn, en), `eval/results/masking_modes.json`

Recall, landmarks excluded; "+ summary" adds the fact-summary fallback when the slot check failed.

| arm | legacy scorer | new scorer | all facts right (new) |
|---|---|---|---|
| plain | 0.674 | 0.701 | 11/90 |
| current masking | 0.755 | 0.759 | 13/90 |
| conditional masking | 0.747 | 0.751 | 13/90 |
| current + summary | 0.851 | 0.854 | 21/90 |
| conditional + summary | 0.828 | 0.831 | 20/90 |

Failed slot checks: 9 of 90 current, 8 of 90 conditional. The scorer fix lifts the plain arm most
(+0.027, only the English target has "No." and "floors" forms). Conditional masking is not better
than current here: -0.008 recall, -0.023 with the fallback, about one to three facts on this sample.
The plain arm (0.674, 67 wrong extras) reproduces `masking_ab.json` exactly. The current-masking arm
gives 0.755 under the legacy scorer against the published 0.747 (13 vs 12 turns right); masking code
and lexicons changed between the two runs and I did not isolate which change moved one turn.

### Translation-safety matrix, all 90 pairs, 20 sentences, 5130 facts, `eval/results/masking_conditional_matrix.json`

"back" is the matrix score (translate, back-translate to English, English extractor); "direct" is
the target-language extractor on the translated text, as in the A/B.

| route | scorer | plain | masked (current) | conditional |
|---|---|---|---|---|
| back | legacy | 0.748 | 0.679 | 0.745 |
| back | new | 0.796 | 0.784 | 0.812 |
| direct | legacy | 0.370 | 0.442 | 0.444 |
| direct | new | 0.374 | 0.445 | 0.447 |

The legacy back row reproduces the published 0.75 / 0.68. About two thirds of the masked loss on the
back route was the scorer: the new extractor lifts masked from 0.679 to 0.784, and plain only from
0.748 to 0.796. With the fixed scorer conditional masking is the best arm on the back route (+0.016
over plain, +0.028 over current) and level with current on the direct route (both about 0.07 above
plain). Slot checks passed on 1740 of 1800 (current) and 1744 of 1800 (conditional) sentences.

Facts missed on the back route by kind (new scorer, plain / current / conditional): gate
399 / 346 / 342, flat 326 / 315 / 309, cross 122 / 198 / 104, main 95 / 120 / 95, block 83 / 62 / 60,
floor 22 / 67 / 55. Conditional repairs cross and main but not floor, where plain is still best; the
floor cause was not isolated.

Power: the collection ran partly on battery (`power_states` in the result file); the outputs are
deterministic greedy decoding, so battery affects time only. Timings were not used.

### Recommendation

Keep the default at `current`. The one test closest to the app (the gold-turn A/B with the fallback)
shows no gain from conditional masking, the matrix gain is on a route that is a proxy, and both
differences are small for these sample sizes. Conditional is the better candidate to switch to: it
removes the "fourth floor reads as 4 floors" failure and wins the matrix, but before it becomes the
default it needs (a) a native speaker to check the restored ordinal forms in each language, since
gender and case agreement are not handled, (b) a floor-specific look at why plain still wins there,
and (c) a run on real recorded speech. The scorer fix should ship regardless.

## Guided-demo set, first pass (held-out, run 2026-11-07)

50 synthetic clips, 5 types (street, apartment, correction, code-mixed, landmark) x 10 languages. The
texts and expected facts were written before the run; the clip set is `demo/clip_set.json`. Each clip
was spoken by Gnani TTS, mixed with street noise, transcribed by Gnani STT, and the facts were read
from the transcript by the production extractor. 5 of the 50 are the earlier demo clips (kept, not
re-recorded); 45 are new. Full 50-row table: `eval/results/demo_set_first_pass.md`.

**First-pass result: 23 of 50 clips have exactly the expected facts (18 of the 45 new clips, plus the
5 earlier ones). 5 clips were not built because Gnani returned a 504 on the transcription call. 22
built clips have a mismatch.** This number is the held-out result and is not edited after the fixes
below; the later re-score is reported separately and is not held-out.

Cost: 130 real Gnani calls (45 clips x 3 calls, less the 5 failed clips' rider-speech call).

### Failures by cause (27 clips)

| cause | clips | count |
|---|---|---|
| Gnani 504 on transcription, clip not built | bn-apartment, bn-mixed, te-correction, pa-mixed, ta-correction | 5 |
| Speech-to-text error (the transcript is wrong) | en-street, en-correction, en-mixed, kn-mixed, mr-street, gu-apartment, mr-apartment, ta-apartment, ml-landmark, ta-landmark, te-landmark, ta-mixed | 12 |
| Spoken-correction parsing ("... 4, sorry, gate 2, not 4" read as a new gate value) | bn-correction, hi-correction, mr-correction, pa-correction, gu-correction | 5 |
| Missing lexicon entry or cue | gu-street, gu-mixed (Gujarati "main"), ml-street (glued cue), mr-mixed, mr-landmark (Marathi has no landmark support) | 5 |

STT errors seen: English ordinals written as fractions ("1/4 main" for "fourth main"), "mail" for
"main", "class" for "cross" in Kannada, a garbled "flat twelve" in gu, mr and ta, "फार्मसी" and
"ஃபார்மசி" rendered as other words, and a truncated "எதிரி" for "எதிரில்". These are properties of the
speech service on this audio, not of Saathi; the extractor correctly reports the facts it cannot
find rather than inventing them. Gate numbers in particular were never invented in the 45 new clips
(every wrong gate is the correction pattern above).

### Fluent but wrong translations (found in the stored translations)

The translator verifier passed both of these; they are the failure mode the card is there to cover,
because a listener reads fluent text.

- `ta-mixed` (Tamil, "opposite the school"): the Marathi translation ends "शाळेचा शत्रू", "enemy of the
  school", because the transcript was cut at "எதிரி" ("enemy").
- `ml-mixed` (Malayalam, "opposite the school"): the Hindi translation ends "स्कूल बनाम", "school
  versus", a literal reading of "എതിർവശം".

The structured facts on the card (cross, main, gate, landmark name) are unaffected by either.

Caveats: one run, one voice per language, synthetic text; bn and hi texts are marked for author
review and the other eight are machine-written and not reviewed by a native speaker; the five earlier
clips were chosen after earlier probes and are not blind.

Three further built clips (hi-landmark, gu-correction, mr-correction, all to Malayalam) were marked
unverified by the translation check and fell back to the facts-only rendering; they are included in
the counts above.

## Guided-demo set, after fixes (not held-out)

The same 50 clips re-scored from the stored speech-to-text transcripts after the fixes below. The
fixes were written while reading these transcripts, so this is a regression check on known data and
must not be quoted as held-out accuracy; the held-out number is the first pass above (23 of 50).
No Gnani calls were made for the re-score. Table: `eval/results/demo_set_after_fixes.md`.

**After fixes: 34 of 50 clips have exactly the expected facts.** The 11 additional clips:

| change | clips that now match |
|---|---|
| Retry of the 5 Gnani 504 clips (8 real calls; bn-apartment, bn-mixed and ta-correction built, te-correction and pa-mixed returned 504 again and were not retried further) | bn-apartment, ta-correction (bn-mixed built but has a transcript error) |
| Spoken "not" corrections: `V R not` and `not R` forms in hi, bn, mr, pa, gu, kn, ta, en | bn-correction, hi-correction, mr-correction, pa-correction, gu-correction, ta-correction |
| Gujarati "main" as the STT writes it (મેઈન) | gu-street, gu-mixed |
| Marathi cue "समोर" and "मागे", also when the STT glues it to the name ("स्कूलसमोर") | mr-mixed, mr-landmark |

Rule for "not": in "gate 2, 4 not" the last value and the "not" are dropped (gate 2); in "gate 4, not
2" the "not" and the value after it are dropped (gate 4). A number that runs into a trigger word
("not 2 floor") is a new fact and is kept, and a compound number ("twenty four not") is not split.
The words are hi नहीं, bn না, mr नाही, pa ਨਹੀਂ, gu નહીં, kn ಅಲ್ಲ, ta இல்லை and English "not".
Kannada had no negation word defined before this change, so it is now handled by the same rule.

Remaining 16 clips, by cause:

| cause | clips |
|---|---|
| Gnani 504 again, not built | te-correction, pa-mixed |
| Speech-to-text error | bn-mixed, en-street, en-correction, en-mixed, kn-mixed, mr-street, gu-apartment, mr-apartment, ta-apartment, te-landmark, ml-landmark, ta-landmark |
| Cue is a real word the STT mangled or glued by sandhi; no ordinary spelling to add | ml-street ("അമ്പലമടുത്ത്"), ta-mixed ("எதிரி", a truncation meaning "enemy") |

No lexicon entry was added for the garbled forms (ഫാമസി, உபானசி, వెనగా, मंदिराज); they are not
ordinary spellings and adding them would teach the extractor the recogniser's mistakes.

### Guided demo after the re-score

The picker lists only clips whose facts match in full (`build_demo_set.py --manifest`, no calls).
The other 16 stay in the eval set. Clips offered per language: bn 4, en 2, gu 4, hi 5, kn 4, ml 3,
mr 3, pa 4, ta 2, te 3 (34 in total). No language has zero.
