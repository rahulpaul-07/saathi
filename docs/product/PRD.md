# Saathi: Product Requirements Document

| | |
|---|---|
| Status | Draft v3, 13 Nov 2026. Written by the author; not yet reviewed by a second person, and no rider has been interviewed. |
| Owner | Rahul Paul |
| Checked against | Repo commit `9929006` (12 Nov 2026) and the live site |
| Companion docs | `docs/DESIGN.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/EVAL.md`, `docs/THREAT_MODEL.md`, `docs/PATH_TO_PRODUCTION.md`, `docs/product/UX_AUDIT.md`, `docs/product/RIDER_INTERVIEWS.md` |

Every claim in this document carries one of three grades. Read the grade before the claim.

| Grade | Meaning |
|---|---|
| **Measured** | A result file in `eval/results/` backs it. Sample size and conditions are stated. |
| **Built** | The code does it and a test covers it. Nobody has measured whether it helps a user. |
| **Assumed** | Nobody has checked it. It is a hypothesis with a named way to test it. |

## 1. Summary

A delivery customer and a rider often share no language. The parts of a direction that decide whether the delivery succeeds (gate, floor, cross, main, block, flat, landmark) are the parts machine translation rewrites without anyone noticing.

Saathi lets the customer speak directions in their own language. The rider sees those facts as large tiles taken from the customer's own words, never from the translation, and hears translated audio as a backup. The rider can confirm or question any tile with one tap.

The engineering is built and measured on synthetic and read speech. The user need is assumed: no rider or customer has been interviewed, and no real phone audio has been tested. The next step is user research and a real-audio test, not more features.

## 2. Problem

| Claim | Grade | Evidence |
|---|---|---|
| A fluent translation can lose address facts | Measured | Plain translation kept 0.70 of facts on 90 text turns (`masking_modes.json`) |
| Fluent-but-wrong output passes automated checks | Measured | Two stored translations passed the placeholder check and read "enemy of the school" and "school versus" for "opposite the school" (`docs/EVAL.md`, "Fluent but wrong translations"; both came from a transcript the speech service cut or misread, and the verifier passed them) |
| Speech recognition garbles address words | Measured | 12 of 27 failing clips on the held-out pass had a wrong transcript: "mail" for "main", "class" for "cross" |
| Riders and customers who share no language struggle with directions | Assumed | No interviews. Test: `docs/product/RIDER_INTERVIEWS.md` |
| A wrong gate costs the rider meaningful time | Assumed | No data. Test: interviews, then partner delivery data |
| Riders would look at a screen during or beside a call | Assumed | No observation. Test: side-channel pilot (section 11, phase 3) |

General interpreters (Google Translate conversation mode, Bhashini, Samsung's interpreter) optimise for a fluent sentence. For directions that is the wrong target: one lost digit sends the rider to the wrong gate.

## 3. Users and jobs

All of this section is **Assumed**.

| User | Situation | Job to be done |
|---|---|---|
| Rider | At a stop or pulled over near the address, phone in hand, speaks a different language from the customer | "Tell me the gate, floor and landmark so I can go straight there, and let me check one thing without typing or a long call." |
| Customer | Waiting for the order, can speak but not in the rider's language | "Let me say the directions once, fix a mistake, and know the rider got it." |
| Delivery partner (future buyer) | Runs the rider app and masked calling | "Cut failed and late deliveries without adding a step for riders or new personal-data risk." |

Roles are independent of languages. Either person can use any of the 10 languages.

## 4. Product principles

These settle arguments when requirements conflict.

1. **Facts over fluency.** The tiles are the product. The translated sentence is a backup.
2. **A missing tile beats a wrong tile.** Extraction is tuned for precision. The customer is told when nothing was found.
3. **The rider never types.** Every rider action is one tap or speech at a stop.
4. **Independence of safety layers.** Tiles never pass through the translator, so one failure cannot corrupt both channels.
5. **Say what is not measured.** Demo clips, beta languages and unreviewed machine text are labelled on screen.
6. **Hold as little personal data as possible.** No accounts, no history, no stored transcripts.

## 5. Goals and non-goals

Goals
1. Critical address facts reach the rider correctly, shown at a glance.
2. Numbers and landmarks survive translation, and the survival rate is measured.
3. The rider can confirm or question a fact with one tap.
4. Any of 10 languages for either role.
5. No address or voice data outlives the conversation.

Non-goals for this version
- Streaming interpretation. Turns are tap to talk.
- Accounts, history, a native app.
- Replacing the masked phone call. Saathi sits beside it.
- Odia, Assamese and Urdu. The speech provider does not support them for both input and output.
- Any claim of safety while riding. The product is for use at a stop.

## 6. Success metrics

No usage metric can be collected today: the app has no metrics endpoint (`docs/PATH_TO_PRODUCTION.md`, section 6). Section 9 specifies the instrumentation.

| Level | Metric | Definition | Today |
|---|---|---|---|
| Outcome | Wrong-gate or wrong-floor rate | Share of deliveries where the rider first went to a wrong gate or floor, with and without Saathi | Unknown. Needs partner data |
| North star (proxy) | Confirmed-address rate | Share of rooms with at least one customer turn that produced facts, where the rider confirmed every tile on the card before the room ended | Not collectable yet |
| Input | Time to confirmed address | First customer turn accepted, to the last tile confirmed | Not collectable. Turn latency alone: median 2.9 s, p95 4.0 s on one laptop GPU, n=20 (**Measured**); translation alone on 2 CPU cores was about 3 s at the median (p95 5.5 to 5.8 s, two runs of n=20, laptop); the hosted VM itself is unmeasured |
| Input | Tile completeness | Share of customer turns where every spoken fact became a tile | 23 of 50 clips exact on a held-out synthetic pass (**Measured**) |
| Input | Ask rate | Asks divided by asks plus confirms | Not collectable |
| Guardrail | Wrong-tile rate | Tiles shown with a value the customer did not say | Tile precision 0.91 clean, 0.84 at 5 dB, n=20 synthetic (**Measured**) |
| Guardrail | Please-repeat rate | Customer turns that returned a repeat prompt | Not collectable |
| Guardrail | Fallback rate by rider language | Turns spoken as the facts-only summary | 24 of 306 stored replays; 21 of the 24 for Bengali and Malayalam riders (**Measured**) |
| Guardrail | Provider cost per conversation | Speech calls times unit rate | Modelled at about 1.5 credits for 6 turns on assumed turn counts; rupee price unknown |
| Counter-metric | Confirm without reading | Confirms within 1 s of a tile appearing | Not collectable. Guards against the north star being inflated by reflex taps |

The north star is a proxy. A confirm tap shows the rider acknowledged a value, not that they reached the right gate. It must be validated against the outcome metric in a pilot before anyone optimises for it.

## 7. User journeys

Each row describes behaviour that is **Built**, read from the code at the commit above.

| Journey | What happens |
|---|---|
| Start | Customer picks a language and creates a room. The screen shows a 6-character code, a rider link and a QR. The rider opens the link (the code is pre-filled), picks a language and joins. A third person is refused (409). |
| Directions | Customer taps, speaks, taps. The card on both screens fills with one tile per fact. The rider hears translated audio and can replay it. |
| Correction | Customer says "sorry, gate 2". Only the gate tile changes and shows "changed, was 4". The marker stays until the rider confirms that tile. A new value for the same fact resets the confirmation. |
| Doubt | Rider taps the question mark on a tile. The customer's copy of that tile shows the rider is asking. Confirm and ask are mutually exclusive. Only the rider can answer the card (403 for the customer). |
| Quick reply | Either side taps one of three fixed phrases. It arrives in the recipient's language with audio. It is never translated at runtime. |
| Nothing found | A customer turn with no address facts returns a "please repeat the address" prompt to the customer. Riders are not prompted, since "coming in 2 minutes" has no address in it. |
| Unchecked translation | If a masked number or address word does not come back from the translator exactly once, the sentence is not spoken. The rider hears a summary built from the facts, and the speaker is asked to repeat slowly. |
| Reload | A reload or dropped connection restores the card, the last turn and the last reply from a state snapshot. |
| End | The customer ends the room, or it expires. The card and audio are wiped from memory. |

## 8. Requirements

Priority: P0 the product fails without it, P1 clearly worse without it, P2 can wait.

### 8.1 Built

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| F1 | Extract the seven fact kinds from the speaker's transcript | P0 | Given a transcript in any of the 10 languages, facts come from the source text only. A fact the rules cannot find produces no tile, never a guess. |
| F2 | Protect numbers and address words in translation | P0 | Each masked slot must return exactly once. Otherwise the turn is marked unverified. |
| F3 | Fact-summary fallback | P0 | An unverified turn is spoken as a summary built from tables; with no facts, the plain translation is spoken. A runaway translation is refused. A translator crash returns a localized error and leaves the room untouched. |
| F4 | Pinned delivery card | P0 | The card holds the latest value per fact kind. Only customer turns update it. Both roles see it in their own labels. |
| F5 | Changed marker | P0 | When a value is replaced, the tile shows the previous value until the rider confirms. An unchanged value does not ask for re-confirmation. |
| F6 | Confirm and ask | P1 | One tap each, rider only, no speech call. A tile not on the card returns 422. |
| F7 | Repeat | P1 | Replays the last audio on the phone with no speech call. |
| F8 | Please-repeat prompts | P1 | Shown to the speaker in their own language for "no facts" (customer only) and "unverified". |
| F9 | Quick replies | P1 | Three fixed phrases per role in 10 languages, each with a review status shown on screen. |
| F10 | Reconnect | P1 | State is restored after a reload within the room's lifetime. |
| F11 | Bad-recording handling | P1 | Empty, non-WAV, under 0.3 s or over 60 s audio is refused before any paid call. A provider 4xx shows "that recording can't be used" and is not retried. |
| F12 | Abuse and spend limits | P1 | Turn and reply rate limits, room caps, upload caps, a daily provider-call budget that fails closed, and a kill switch that needs no restart. |
| F13 | Zero-cost guided demo | P1 | Stored clips replay through the real screens with no provider call. A clip outside the bundle is refused, never sent live. |
| F14 | Privacy by construction | P0 | Rooms live in memory and expire. Transcripts and card content are never logged or written to disk. |

### 8.2 Gaps

| ID | Requirement | Pri | Why | Acceptance criteria |
|---|---|---|---|---|
| G1 | Rider reply controls reachable without scrolling | P1 | On a 412 px phone, four tiles push quick replies and the microphone below the fold. Only the customer's microphone is pinned. | At 360 x 740 with four tiles on the card, Repeat and all three quick replies are inside the viewport. Existing 48 px target and focus-not-obscured tests still pass. |
| G2 | Link-first rider join | P1 | The code pre-fills from the link, but the screen still leads with a text field. | When the code arrives from the link, the first control is language, and the code is shown as filled. Manual entry remains available. |
| G3 | Content-free instrumentation | P0 for any pilot | Section 6 cannot be measured. | Events in section 9 are emitted behind a flag. A test asserts no event carries a transcript, a fact value, a room code or an IP address. |
| G4 | Real-audio evaluation | P0 for any pilot | All speech tested is synthetic or read. | Consented recordings of real directions on phone microphones, scored with the existing harness, reported next to the synthetic numbers. |
| G5 | Native-speaker review | P0 for any pilot | Only Bengali and Hindi text is author-reviewed. Eight languages, Kannada included, are unreviewed machine output. | Each launch language has its interface strings, quick replies, repeat prompts and lexicon reviewed by a native speaker, with status flipped from "pending". |
| G6 | Consent notice before the customer speaks | P0 for any pilot | Voice goes to a third-party speech provider. | A notice in the customer's language states what is sent and kept. Declining still lets the delivery proceed. |
| G7 | Number words above 20 in six languages | P2 | Tamil, Telugu, Gujarati, Malayalam, Marathi and Punjabi number words were probed only up to 20. | A flat or floor above 20 spoken in each language yields the right tile on a held-out clip. |
| G8 | Hosted latency measurement | P1 | The live site translates on 2 CPU cores. A 2-core run on a laptop exists, but the hosted VM has never been timed end to end. | Median and p95 turn time on the hosted machine, n of at least 20, published in `docs/EVAL.md`. |

## 9. Instrumentation specification (not built)

Counts and durations only. No transcript, fact value, landmark name, room code, token or IP address in any event.

| Event | Properties | Answers |
|---|---|---|
| `room_created` | customer language | Volume by language |
| `rider_joined` | rider language, seconds since creation, joined by link or by typed code | Join friction (G2) |
| `turn_completed` | speaker role, language pair, number of facts by kind, verified flag, stage timings | Tile completeness, fallback rate, latency |
| `turn_failed` | reason: bad recording, no speech, provider busy, budget spent, runaway, translator down | Reliability |
| `repeat_prompt_shown` | reason: no facts or unverified | Please-repeat rate |
| `card_changed` | fact kind | How often customers correct themselves |
| `chip_confirmed` | fact kind, whether it was a changed tile, seconds since the tile appeared | North star, counter-metric |
| `chip_asked` | fact kind | Which facts riders doubt |
| `quick_reply_sent` | phrase id, sender role | Which phrases earn their place |
| `room_closed` | reason: ended, idle, hard limit; duration; turns; whether every tile was confirmed | North star |

## 10. Alternatives considered

| Alternative | Why not |
|---|---|
| Translate and speak, with no tiles | Measured fact recall of 0.70 with plain translation. A lost digit is silent. |
| Take tiles from the translation | Ties both channels to the same failure. |
| A hosted LLM for extraction or translation | Adds latency and cost, sends addresses to another party, and can rewrite an address, which is the failure being guarded against. |
| A fine-tuned tagger | 30 gold utterances cannot train or validate one. |
| Free-text chat between rider and customer | The rider would type. |
| Accounts and history | Stored addresses with no benefit to a single delivery. |
| Bridging the phone call with a live translated voice | Needs streaming speech contracts, barge-in and echo control, and untested 8 kHz audio. Kept as a later option. |

## 11. Launch plan

Each phase has an exit gate. The thresholds are proposals to argue about, set from the measured baselines, and should be revised after phase 1.

| Phase | Work | Exit gate |
|---|---|---|
| 0. Now | Synthetic and read-speech evaluation, public demo with a spend budget | Done |
| 1. Discovery | 3 to 5 rider interviews and a few customer conversations. Show the rider screen on a phone outdoors. | The problem in section 2 is confirmed or this PRD is rewritten. Tile order and quick-reply set are revised from what riders said. |
| 2. Real audio | G4 and G5 for the launch languages. Fix G1 and G2. Two real phones on one network with a speaker of each language. | Proposed: wrong-tile rate at or below 5% on real phone audio. A wrong tile is the worst failure. This is stricter than today: clean synthetic precision is 0.91, so about 9% of tiles are wrong even before real-phone noise, and the gate would need a measured improvement, not just a re-run. Median hosted turn time measured (G8). |
| 3. Side-channel pilot | One partner, one city, two or three language pairs. The link goes out with the order; the masked call is untouched. G3 and G6 shipped. | Riders open the link and confirm tiles without being told to. Confirmed-address rate tracks the partner's wrong-gate data closely enough to trust as a proxy. |
| 4. Expand | More languages as each passes G5. Decide on the IVR or call-bridge options. | Outcome metric improves against a control group. |

Rollback at any phase is the existing kill switch, which stops live speech without a restart and leaves the guided demo working.

## 12. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The need is not real: riders cope with a call today | Unknown | Fatal | Phase 1 before any more building |
| Real phone audio is much worse than synthetic | High. Recall already falls from 0.84 to 0.64 at 5 dB synthetic noise | High | Phase 2 gate; confirm and ask exist for this case |
| A rider trusts a wrong tile | Medium | High | Precision bias, changed marker, "check this" flag on uncertain tiles |
| Riders use it while moving | Medium | High | Copy says "use when stopped". Needs a partner policy decision, not just copy |
| Bengali and Malayalam riders get a worse experience | Measured in replay | Medium | Track fallback rate by language; do not launch a language that fails its gate |
| Provider outage or rate limit | Measured: intermittent 504s in long runs | Medium | One retry and a clear message. Confirm, ask and Repeat need no provider call; quick replies need none once their audio is cached |
| Personal data obligations under the DPDP Act | Certain for a real launch | High | G6, a processing agreement with the speech provider, legal review. None done |
| A partner wants it inside its own app | High | Medium | Server-to-server room creation and signed links are designed in `docs/PATH_TO_PRODUCTION.md`, not built |

## 13. Open questions

| Question | Owner | How it gets answered |
|---|---|---|
| Do riders struggle with cross-language directions, and what do they do today? | Rahul | Phase 1 interviews |
| Which fact do riders look for first? | Rahul | Phase 1, walk through their last hard delivery |
| Is one confirm per tile right, or one "all clear" for the card? | Rahul | Phase 1 observation, then `chip_confirmed` data |
| Should a tile be shown when the system is unsure, or held back? | Rahul | Compare ask rate and wrong-tile rate in phase 3 |
| What does a conversation cost in rupees? | Rahul | Price per credit from the provider contract |
| Who sends the customer link: the partner's SMS or its app? | Partner | Phase 3 scoping |

## 14. Documentation inconsistencies found in this review

Eight places where the repo's own documents disagreed with the code or with each other were found while writing this PRD, and fixed on 13 Nov 2026: the "changed" marker lifetime (`DESIGN.md`), room expiry times (README), the public deployment status (`PATH_TO_PRODUCTION.md`, `DESIGN.md`, `DESIGN_FAQ.md`, `LAN_CHECK.md`), Telugu's tier (`DESIGN_FAQ.md`), the 67% figure (now 70%, from 0.701), and the translator-failure wording in `CHANGELOG.md` (a failed placeholder check gives the fact summary; an unavailable translator gives a localized 502). The commit that fixed them shows each change.
