# Saathi

Delivery-directions interpreter: a customer gives directions by voice, a rider in another Indian
language gets the critical facts (gate, floor, cross/main, landmark) as big chips plus translated
audio, in a short-lived room. Gnani STT/TTS plus local IndicTrans2, any-to-any across the 10
languages Gnani supports for both (bn en gu hi kn ml mr pa ta te). Direction change of 2026-10-12;
see docs/DESIGN.md.

This file is the shared instruction file for every coding agent used on this repo
(Claude Code, Codex, Copilot, Cursor). Keep it accurate and short.

## Context

- Purpose: portfolio project
- Deadline: none
- Working mode: BALANCED

## Commands (Windows PowerShell)

- Install: `uv sync` (see README "Slow connection" if torch stalls, then use `--no-sync`)
- Run: `uv run --no-sync uvicorn saathi.app:create_app --factory --port 8000`
- Test: `uv run --no-sync pytest` (`-m model` for the real model)
- Lint and typecheck: `uv run --no-sync ruff check . ; uv run --no-sync mypy src tests scripts`
- UI (dev tooling, `npm ci` once): `npm run typecheck`, `npm test`, `npm run e2e`

## Layout

- `src/saathi/` - FastAPI app, pipeline, Gnani client, translator
- `src/saathi/static/` - browser UI (plain ES modules, JSDoc types)
- `tests/` - pytest with injected fakes (no network or GPU)
- `scripts/` - smoke test against the real Gnani APIs (spends credits)
- `docs/DESIGN.md` - architecture, data flow and the slice plan; read before large changes
- `docs/DECISIONS.md` - why things are the way they are
- `docs/HANDOFF.md` - if present, read it first: where the last session stopped

## Rules for this repo

- Follow `docs/DESIGN.md`; record non-obvious decisions in `docs/DECISIONS.md`.
- Configuration comes from environment variables listed in `.env.example`. Never commit
  or print secrets, and never read `.env`.
- Every change keeps the app runnable and the tests green.
- The human makes all git commits. Agents propose commit groups and messages only.
- Real Gnani calls spend credits and hit rate limits; tests use fakes. Eval calls go through the
  ledger (hard cap in `evaluation/calls.py`), run `--dry-run` first, and only while the author is awake.
- Addresses are personal data: synthetic addresses only in tests, eval and demos; never log or
  store transcripts; rooms are in memory and expire. Recordings of people stay in `eval/audio/`
  (gitignored) and are reported as "consented human speech".
- Language support is data in one table (`languages.py`), never per-language branches.
- Tiers: kn, en, hi, bn verified; te reviewed; gu, ml, mr, pa, ta beta (labelled in UI and README).
- No hosted LLM. Cut order if time runs out: localized labels first; never the chips or the minimal quick replies (3 phrases in en, kn, hi, bn).

## Out of scope

- Streaming interpretation, accounts, history, public deployment or tunnels, free-speech replies
  from the rider, Odia, Assamese and Urdu (Gnani supports none), RNNoise and a local LLM (deferred).
