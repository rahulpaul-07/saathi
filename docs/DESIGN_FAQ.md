# Design FAQ

Questions an interviewer is likely to ask about Saathi, with short answers grounded in this repo.
Numbers come from `docs/EVAL.md`; where a number has a caveat the answer says so.

## The idea

**1. What problem does it solve?**
A delivery rider and a customer often share no language, and the facts that matter (gate, floor,
cross, main, landmark) are exactly what machine translation damages. Saathi shows the rider those
facts as chips taken from what the customer said, and adds translated audio as a backup.

**2. Why not just translate and speak?**
Because a fluent translation can still be wrong. On the gold turns, plain translation kept 70% of
the facts (0.701); even with masking and a fallback it kept 85% (0.854). One lost digit sends the
rider to the wrong gate, so the chips cannot depend on the translator.

**3. Why chips from the transcript and not from the translation?**
Independence. The chips come from the speech-to-text transcript in the speaker's own language, so a
wrong or looping translation sits next to correct chips. The cost is that the extractor needs rules
for each language (lexicons), which is real work and only machine-verified (no native reader) for the six beta languages.

**4. Why no LLM?**
A hosted LLM adds latency, cost and a place for addresses to leave the machine, and an LLM that
rewrites an address is the failure we are guarding against. Extraction is rules plus tables you can
read and test; translation is a local model. A local LLM is deferred, not rejected.

**5. Why rooms instead of a phone call or an app with accounts?**
It is the smallest thing that lets two people talk without either installing anything: a 6-character
code, a random token each, memory only, and expiry. No accounts or history also means no stored
addresses. `PATH_TO_PRODUCTION.md` says what a real deployment needs instead.

## Design choices

**6. Why IndicTrans2 and not a cloud translator?**
It covers all ten languages in any direction, runs locally (no addresses leave the machine for
translation), and fits a 6 GB laptop GPU: three distilled models use about 1.4 GB in fp16. The cost
is that it is a research model that sometimes loops; a runaway guard catches that (15 runaways in
1012 sentences for bn to kn).

**7. Why three models?**
IndicTrans2 ships separate Indic-to-Indic, English-to-Indic and Indic-to-English models. Routing is
data in `languages.py`, so adding a language is a table row, not a branch.

**8. Why do roles not tie to languages?**
Any customer language can meet any rider language, and either side can speak or send a quick reply.
Hard-coding "customer speaks Kannada, rider speaks Hindi" would make the demo look good and the
product wrong. Pairs in tests and demos are examples only, and the design rule in `docs/DESIGN.md` forbids tying
them.

**9. How does masking work and why placeholders like `#L51`?**
Numbers and address loanwords are replaced by numbered placeholders before translation and put back
after, in plain digits and the listener's script. `#L51` was chosen by probing: 29 of 30 translations
returned every slot once, against 12 of 30 for `<ID1>`, because the toolkit wraps `#word` tokens in
its own entity that the model was trained to copy. A translation that loses a slot is not spoken.

**10. What happens when the translation fails the check?**
The app speaks a fact summary built from tables ("2 cross, 3 main, gate 2, landmark ...") instead of
the sentence, and says the translation could not be fully checked. With no facts it falls back to the
plain translation. Fallback and chips are the safety layer, not the fluent sentence.

**11. Why a pinned card with "changed, was X" and confirm/ask?**
People correct themselves ("gate 2, no, gate 4"). A card that silently replaces the value hides that.
The changed marker stays until the rider confirms; the rider can ask about one chip with a tap. Both
are one-tap, need no speech and cost no Gnani call.

**12. Why SSE and not WebSockets?**
Traffic is one-way per participant (server to browser); uploads are plain POSTs. SSE is simpler and
survives proxies. Tokens are bearer headers, so the browser reads the stream with `fetch`, not
`EventSource`, and reconnects with backoff and jitter.

**13. How are language tiers decided?**
By evidence, not by how good the language is. kn, en, hi and bn have native-word extraction rules
and the synthetic gold set; gu, ml, mr, pa, ta and te are beta (machine-verified only). The tier is
shown in the UI. Machine-verified means each lexicon entry is a spelling the real STT wrote when it
heard Gnani TTS speech; no native reader has checked them.

## Evidence and what went wrong

**14. What is your headline result?**
Fact recall on the gold turns goes from 0.701 (plain) to 0.759 (masked) to 0.854 (masked plus
fallback), 90 turns, text only, scored with the extractor fixed on 2026-11-01 (the old scorer gave
0.674, 0.747, 0.843). Under street noise at 5 dB, address-fact recall on synthetic speech
drops by 0.20 (95% CI 0.09 to 0.31, n=20). The live smoke test through the real API passed all 9
steps. Each has caveats in `EVAL.md`: synthetic speech, our gold text, small samples.

**15. The 0.808 number: what happened?**
The first masking A/B recorded B = 0.808 (4 of 90 failed checks). When I re-ran the same script on
current code and on the original commit's sources it gave 0.747 with the old scorer (9 to 10 of 90 failed). The cause is
unknown: an earlier file state or nondeterminism are the candidates. I corrected the README, EVAL and
the result file, kept the old file in git history, and the claim became a 7-point gain instead of 13.
Lesson: rerun a headline number before it goes in a README, and say when it does not reproduce.

**16. What was the masking reversal?**
In the 10 x 10 translation matrix masking scored lower than plain (0.68 against 0.75 with the old scorer; 0.784 against 0.796 with the fixed one), the opposite of
the A/B. My first hypothesis (the matrix source text has digits where STT gives words) was not
supported. The diagnosis: the restore writes a bare digit, so "fourth floor" comes back as "4 floors"
and the back-translation reads a quantity; part of the gap was a strict English extractor that misses
"Gate No. 2". The two experiments score different routes (back-translation versus the target-language
extractor), so neither is "the" accuracy. Conditional masking is the proposed fix, evaluated behind
a flag and not made the default (see `EVAL.md`).

**17. Tell me about a bug your tests missed.**
On the demo split-screen page the rider's room code was never filled in. The code tested
`input instanceof HTMLInputElement`, but the element belongs to the iframe's window, so the check was
always false. The existing e2e test passed: it read the code immediately after the click, got an
empty string, and compared it to the rider's empty input. It now waits for a real 6-character code.
The journey test that found it runs the whole path in a browser.

**18. Other tests that passed for the wrong reason?**
Yes, two kinds. A leak test read `#code` before it was filled. And the fake Gnani clients accepted
empty or invalid audio, so a rehearsal that sent a bad recording (two 400s from Gnani) had no test
that could have caught it; the fakes now refuse empty or non-WAV audio with a 400, as Gnani does.
The habit I took from it: for each test ask what a broken implementation would do, and make the test
fail on that.

**19. What did the live rehearsal teach you?**
That the error path matters as much as the happy path: a bad recording used to cost two Gnani calls
and end in "speech service not responding". Now the route rejects empty or tiny audio before any
call, and a Gnani 4xx becomes a localized "that recording can't be used" that the client does not
retry. I could not reproduce why the demo clip was not fetched and say so in the handoff.

**20. What would you do next?**
Re-measure latency at other times of day (the 2026-11-01 run gave p95 4.0 s, an earlier one 11.3 s
during a stretch of Gnani 504s); get
native speakers to review the bn and hi phrases beyond the ones done and the beta languages; test on
two real phones over a LAN; collect consented real address speech; and decide conditional masking
from a larger evaluation.

## Safety and engineering

**21. How do you handle personal data?**
Addresses are personal data. Rooms are in memory and expire (30 minutes idle, 2 hours hard),
transcripts are never logged or stored, tests, evaluations and demos use synthetic addresses, and
the API key is a `SecretStr` that never reaches a log (tested). `THREAT_MODEL.md` lists what is and
is not defended.

**22. What are the main abuse risks?**
Guessing room codes (6 characters, at most 50 live rooms, rate limited), token theft (CSP, no inline
script, textContent-only rendering), credit burn (per-IP and per-participant limits, bounded uploads,
a hard cap and ledger for evaluation), and SSE exhaustion (bounded queues). It has had no external
review.

**23. How do you control Gnani spend?**
Every evaluation call goes through a persisted ledger with a hard cap in `evaluation/calls.py`;
every script has `--dry-run` that prints the plan first; failed and retried calls count. Tests use
fakes with no network.

**24. How is it tested?**
pytest with injected fakes (no network, no GPU) for the backend; node tests for pure UI modules;
Playwright for the browser with two contexts, fake Gnani and a fake translator, including 10
language-pair journeys and contrast checks in both themes. A live smoke through the real
API spends a few credits and is run by hand. Real phones and real human address speech are not
tested.

**25. Is this production-ready?**
No, and `PATH_TO_PRODUCTION.md` says why: it is one process with in-memory rooms, a small public deployment with a daily budget, no
accounts, one machine's GPU, no external security review, no native-speaker review for most
languages, and no integration with a delivery partner. It is a portfolio project that shows the
approach and measures it honestly.
