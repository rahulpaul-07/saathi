# Handoff

## Where we are
Slices 1-4 are built (slice 4's Android phone check is still open). Slice 5 (evaluation) is
half done: the translation evaluation ran and is written up in docs/EVAL.md; the Gnani-backed
steps are built and tested with fakes but have NOT been run. **No Gnani call has been made**
(ledger spent: 0).

## Slice 5: results so far (all on AC power, RTX 3050)
- Greedy vs beam5, 12 pairs x 50 sentences: beam5 gains +0.32 chrF++ on the app pairs (95% CI
  -0.49 to +1.07) for +285 ms, is worse on bn->kn (43.9 to 41.6), and had 4 runaways in 600
  against greedy's 0. Recommendation: keep greedy.
- Guard: 0 false flags (0 of 1012 FLORES references per language).
- **Surprise: greedy bn->kn ran away 15 times in 1012 sentences (1.5%)** on the full devtest;
  the 50-sample had shown 0. The guard catches them, but the app will hit this often on its main
  pair. Details in docs/EVAL.md.
- Token ratio of non-runaway outputs peaks at 1.50 (Tamil), so the 2x cap has headroom.
- Phone cases 1 and 2 run as text (docs/EVAL.md). Case 1 garbled input loops under greedy and not
  under beam5; case 2 is a shared translator word-sense error.

## What I built
`src/saathi/evaluation/` (metrics, FLORES loader, power guard, Gnani call ledger and limiter,
turn runner, STT scoring, start-of-clip analysis), `translate_with_stats` in translate.py,
scripts `fetch_flores.py`, `eval_translation.py`, `eval_report.py`, `eval_phone_cases.py`,
`eval_turns.py`. Verified: pytest 111 passed (10 model tests deselected), ruff check and format
clean, mypy clean over src tests scripts. Not verified: `eval_turns.py synth/latency/stt-real`
against real Gnani (only `plan`, `sentences` and the fake-driven unit tests ran).

## Things to know
- I added a wait-for-AC (up to 8 h) to `eval_translation.py`. The latency and stt-real steps
  refuse to start off AC instead (`--allow-battery` tags results as battery).
- Call plan is 132 expected (40 TTS, 82 for 41 turns, 10 STT), cap 155. My first plan spaced
  turns 6 s apart, which would put 4 calls in a 10 s window; the limiter now allows 3 per 10 s.
- I did not add a `sounddevice` recording script (new dependency, unapproved). Recording uses
  Audacity (docs/EVAL.md). Decision for you: add `sounddevice` if you want a script.
- Some FLORES bn lines carry stray quote marks (for example `"""...`), also in the reading list.
- The published IndicTrans2 comparison is not done (paper PDF unreadable here); open item.

## For the morning (in order, plug in AC first)
1. `uv run --no-sync python scripts/eval_turns.py plan` (free).
2. `... synth --limit 2`: checks Gnani TTS accepts these long sentences (2 calls). Then `synth`
   (38 more). Stop and tell me if a sentence is rejected for length.
3. `... latency` (82 calls, about 7 min with the pacing).
4. Record the 10 clips listed in `eval/audio/real/sentences.txt` (docs/EVAL.md), then
   `... stt-real` (10 calls).
5. `... report`, then fill the "pending" section of docs/EVAL.md from `stt_summary.md`.
6. Decide: run beam5 on the full bn->kn devtest (about 20 min, no Gnani) to see whether beam
   fixes the 1.5% greedy runaways; and whether to add `no_repeat_ngram_size` (deferred earlier in
   DECISIONS.md pending this eval, whose chrF cost can now be measured).

## Proposed commits (you run them)
1. `build(deps): pin sacrebleu for chrF++` : pyproject.toml, uv.lock
2. `feat(translate): add translate_with_stats for eval token counts` : src/saathi/translate.py,
   tests/test_translate.py
3. `feat(eval): add evaluation package with metrics, pacing and power guard` :
   src/saathi/evaluation/, tests/test_eval_*.py
4. `feat(eval): add FLORES translation eval, phone cases and Gnani turn scripts` : scripts/,
   .gitignore
5. `docs(eval): record slice 5 translation results, decisions and handoff` : eval/results/,
   docs/EVAL.md, docs/DECISIONS.md, docs/DESIGN.md, docs/HANDOFF.md
   (eval/results holds FLORES-derived outputs, CC BY-SA 4.0; EVAL.md carries the attribution.)

## Open from slice 4
- Phone check (README "Run the UI"), the 60 s auto-stop and mic-denied paths are not
  browser-tested, a retry re-runs STT, and `GET /turn` returns 404.
