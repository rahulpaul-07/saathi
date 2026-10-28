# Handoff

Source of truth: docs/DESIGN.md, docs/DECISIONS.md, AGENTS.md (delivery-rider bridge, approved
2026-10-12). The previous handoff (old slice 5) is obsolete and was replaced.

## Where we are: slice 0, partly done
Done and tested (no Gnani calls made this session; credits 4,991 of 5,000 left, cap 290 approved):
1. 10-language table with tiers: `src/saathi/languages.py`, tests in `tests/test_languages.py`.
2. Three-model routing: `route_for` and `RoutingTranslator` in `src/saathi/translate.py`. Tests
   cover all 90 ordered pairs and dispatch to the right model.

## BLOCKED: Hugging Face access to the two English models
`ai4bharat/indictrans2-en-indic-dist-200M` and `ai4bharat/indictrans2-indic-en-dist-200M` are
gated repos and the author's account is not authorized for them (403 on config.json; the local
cache holds only empty LICENSE/README stubs). Only indic-indic-dist-320M is downloaded. Action
for the author: request access on both model pages (same as for indic-indic, see README), then
`uv run hf auth login` if needed. Blocks:
- VRAM with all three loaded (item 3).
- Quick-reply machine translations (item 5): en -> 10 languages needs the en-indic model.
- "en-to-hi/bn and a rider-side route working locally" in the slice 0 row of DESIGN.md.

## VRAM so far (RTX 3050 6 GB, AC power, `scripts/measure_vram.py`)
Measured with indic-indic only: 613 MiB weights, 625 MiB torch peak after a short translation,
device-wide 982 MiB before any load (CUDA context and desktop) and 1644 MiB after. The two 200M
models are NOT measured; roughly 400 MiB each by parameter count (inferred, not verified), which
would put all three near 2.5 GB of 6.1 GB. Re-run with no arguments once access is granted:
`uv run --no-sync python scripts/measure_vram.py`.

## Next steps
1. Author gets HF access; run the VRAM script with all three routes; record the peak and the
   headroom verdict (TTS/STT are remote Gnani APIs, so only a browser and the desktop compete).
2. Write the quick-reply table (3 phrases x 10 languages, review flag per language); send the
   author the bn and hi versions with the English meaning for review.
3. Then slice 1 per DESIGN.md (fact extractor; Kannada and Telugu recording scripts due Oct 13).

## Checks at end of this session
pytest 122 passed; tsc and npm test (14) pass. See the final message for ruff and mypy.
