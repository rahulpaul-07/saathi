# Saathi: one-page brief

**What it is.** A customer speaks delivery directions in their own language. The rider, in another Indian language, sees the gate, floor, cross, main and landmark as large tiles and hears translated audio. Live at https://saathi.indiasouthcentral.cloudapp.azure.com.

**The problem.** A fluent translation can still send a rider to the wrong gate. Numbers and local address words are what machine translation rewrites without anyone noticing. On 90 test turns, plain translation kept 70% of address facts.

**The bet.** Take the facts from what the customer said, not from the translation, and let the rider confirm or question each one with a tap. The two channels fail independently, so a bad translation still sits next to correct tiles.

**What is proven (synthetic and read speech only).**

| Result | Number |
|---|---|
| Fact recall: plain, masked, masked plus fallback | 0.70, 0.76, 0.85 (90 text turns) |
| Clips with exactly the right facts, held-out first pass | 23 of 50 |
| Speech error rate on real read speech | 0.067 (100 clips), 0.101 at 5 dB noise |
| Median turn time | 2.9 s, p95 4.0 s (one laptop GPU, n=20) |
| Language pairs passing stored replay | 90 of 90 |

**What is not proven.** That riders have this problem often enough to change behaviour. That it works on real phone audio in traffic. That any language other than Bengali and Hindi reads correctly to a native speaker. No rider has been interviewed.

**Who would buy it.** A delivery platform, as a link sent with the order that sits beside its masked call. Not a consumer app.

**Why it might not matter.** Google Translate now offers live two-way conversation in India across more than 70 languages. Saathi only earns a place if structured, confirmable address facts beat a general interpreter for this one job. That is an untested claim. See `COMPETITIVE_ANALYSIS.md`.

**The ask.** Four things before any pilot, in order: rider interviews, a real-audio test, native-speaker review of the launch languages, and content-free instrumentation. Details in `PRD.md` section 11 and `ROADMAP.md`.

**Where everything is.** All of these are in this folder: `PRD.md` (requirements, metrics, launch gates), `COMPETITIVE_ANALYSIS.md`, `MARKET_SIZING.md`, `ROADMAP.md`, `BACKLOG.md`, `PILOT_EXPERIMENT.md`, `UX_AUDIT.md` and `RIDER_INTERVIEWS.md` (the discovery guide; no interviews have been run yet).
