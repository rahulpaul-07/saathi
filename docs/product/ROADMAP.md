# Saathi: roadmap

Date: 13 Nov 2026. Outcome-based: each item states what it should change and how we would know. No dates are promised; the order is the commitment. IDs refer to `PRD.md` section 8.2 and `BACKLOG.md`.

## How items were ranked

Three questions, in this order:

1. **Does it reduce the biggest unknown?** The biggest unknown is whether the problem is real. Learning beats building until that is answered.
2. **Is it required before real users touch the product?** Consent, review and measurement come before polish.
3. **Impact for effort,** judged from the code. S is under half a day, M is one to two days, L is more.

Confidence is how sure I am the item will have its stated effect. Low confidence is a reason to test, not to skip.

## Now: learn whether the problem is real

| Item | Outcome | Effort | Confidence | Why now |
|---|---|---|---|---|
| Rider and customer interviews | The problem statement is confirmed, changed or dropped | M | n/a | Everything else depends on it |
| Head-to-head against Google Live translate on the 50 demo clips | Know whether a general interpreter already keeps the facts | S | n/a | Decides whether the core bet stands |
| Fix the eight doc inconsistencies (PRD section 14) | Docs match the code | S | High | Credibility; costs an hour |
| G1: pin the rider's reply controls | Replies reachable without scrolling | S | High | Already designed; closes a gap against the product's own goal |
| G2: link-first rider join | No typing on the main path | S | High | Same |

## Next: make it safe to put in front of real people

| Item | Outcome | Effort | Confidence | Depends on |
|---|---|---|---|---|
| G4: real-audio evaluation | Fact precision and recall on real phone recordings | L | n/a | Consented recordings |
| G5: native-speaker review of launch languages | No unreviewed text in a launch language | M per language | High | Finding reviewers |
| G3: content-free instrumentation | The PRD metrics become collectable | M | High | None |
| G6: consent notice | Customer knows what is sent before speaking | S | High | Copy reviewed per language |
| G8: hosted latency | Know real turn time on the deployed machine | S | n/a | None |
| Two-phone check on a local network | First real-device run with a speaker of each language | S | n/a | `docs/LAN_CHECK.md` |

## Later: only if Now and Next say yes

| Item | Outcome | Effort | Note |
|---|---|---|---|
| Partner room creation and signed links | A platform can start a room from an order with no code | L | Designed in `docs/PATH_TO_PRODUCTION.md` |
| Side-channel pilot | Evidence on wrong-gate rate | L | `PILOT_EXPERIMENT.md` |
| Shared state for more than one process | Survives a restart, scales past one machine | L | Redis design exists on paper |
| G7: number words above 20 in six languages | High floors and flat numbers read correctly | M | Needs probe budget |
| IVR capture of the address | Customer says the address once by phone | L | Needs 8 kHz audio testing first |

## Deliberately not planned

| Item | Why not |
|---|---|
| More languages | Ten is already more than can be reviewed. Depth before breadth. |
| A native app | A link needs no install. Revisit only if a partner cannot embed a web view. |
| A hosted LLM | It can rewrite an address, and it sends addresses to another party. |
| Live call bridging | Needs streaming contracts and echo control. Only after the side channel proves riders use the tiles. |
| More quick replies | Each phrase needs review in ten languages. Add from interview evidence, not guesses. |

## Kill criteria

Stop, and say so, if any of these holds after the Now stage:

- Riders report that a call or the security guard reliably resolves directions.
- Live translate keeps every fact on the demo clips and riders see no value in confirming tiles.
- No platform contact shows interest in a side-channel test.
