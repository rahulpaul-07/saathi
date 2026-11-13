# Saathi: pilot experiment design

Date: 13 Nov 2026. A design, not a plan with a partner behind it. No partner exists. Every number below marked "illustrative" is there to show the arithmetic and must be replaced with the partner's real baseline.

## Question

Does sending a Saathi link with the order reduce wrong-gate and wrong-floor deliveries when the rider and customer share no language?

## Hypotheses

| | Statement | Metric |
|---|---|---|
| H1 (primary) | Riders with the link go to a wrong gate or floor less often | Wrong-gate rate |
| H2 | They reach the door sooner after arriving at the address | Minutes from "arrived" to "delivered" |
| H3 | They need fewer calls | Masked calls per order |
| H0 | No difference | |

## Design

| Choice | Decision | Why |
|---|---|---|
| Unit of randomisation | The rider, not the order | A rider who has used the tiles behaves differently on the next order. Randomising orders would contaminate the control group. |
| Arms | Control: today's flow. Treatment: link sent with the order, masked call unchanged | Tests the side channel only; nothing is taken away from anyone |
| Eligibility | Orders where the rider's and customer's app languages differ, in one city, to addresses flagged as apartments or gated communities | That is where the problem is assumed to be. Language set in the app is a proxy for language spoken, and a weak one. |
| Languages | Two or three pairs that have passed native review | Do not launch a language that fails its gate |
| Duration | At least two full weeks | Covers weekday and weekend patterns and lets novelty wear off |
| Analysis | Compare rates between arms with riders as clusters; report the interval, not only a p-value | Orders from one rider are not independent |

## Measuring the outcome

Wrong-gate rate is not something a platform logs directly. Options, best first:

1. A one-tap rider question after delivery: "Did you go to the wrong gate or floor first?" Cheap, but self-reported.
2. GPS dwell: time within the address radius before delivery. Objective, but noisy and it mixes in lift waits and security checks.
3. Support contacts and customer complaints mentioning location. Sparse.

Use 1 as the primary measure and 2 as a check that it moves the same way.

## How many orders

For comparing two proportions with 80% power at a 5% two-sided significance level, a standard rule of thumb is:

```
orders per arm ≈ 16 x p x (1 - p) / d²
```

where `p` is the baseline rate and `d` is the smallest change worth detecting.

Illustrative only: if the baseline wrong-gate rate were 10% and a drop to 7% were worth acting on, then p = 0.10 and d = 0.03, giving 16 x 0.10 x 0.90 / 0.0009 = 1,600 orders per arm.

Because riders are the unit, that count must be multiplied by a design effect, `1 + (m - 1) x ICC`, where `m` is orders per rider and ICC is how alike one rider's orders are. With 20 orders per rider and an ICC of 0.05 (both illustrative) the multiplier is 1.95, so about 3,100 orders per arm. The real baseline and ICC come from the partner's history before the pilot starts.

If the baseline rate turns out to be 2%, the same arithmetic needs far more orders to detect a realistic change, and the pilot may not be worth running. That is worth knowing before starting.

## Guardrails: stop the pilot if

| Guardrail | Threshold |
|---|---|
| Delivery time in treatment is worse than control | Any consistent increase |
| A rider reports using it while moving | One credible report triggers a review |
| Wrong-tile reports | More than a handful in the first week; each one is read by a person |
| Provider failures | Turns failing at a rate that makes the link unreliable |
| A privacy complaint | One |

The kill switch stops live speech without a restart.

## Secondary measures (from the instrumentation spec)

Link open rate, share of opened rooms with at least one customer turn, confirmed-address rate, ask rate by fact kind, please-repeat rate, fallback rate by rider language, time from first turn to last confirm.

Adoption comes first. If riders do not open the link, H1 cannot be tested and the finding is "the side channel is not used", which is still a result.

## What each outcome means

| Result | Decision |
|---|---|
| Riders do not open the link | The side channel is wrong. Consider putting the card inside the rider app's order screen. |
| Riders open it, wrong-gate rate does not move | The tiles are not adding to what the call already does. Stop or narrow to corrections only. |
| Wrong-gate rate falls and time does not rise | Expand languages and cities; build partner room creation. |
| Wrong-gate rate falls but delivery time rises | Look at where the time goes. Probably the customer's speaking step. |

## Threats to validity

- **Novelty.** Riders try a new thing for a week. Compare week one with week two.
- **Selection.** Customers who bother to speak directions may differ from those who do not. Analyse by assignment, not by use.
- **Proxy for language.** App language is not spoken language.
- **Self-report.** Riders may under-report wrong gates. The GPS check exists for this.
- **One city.** Address conventions differ; "cross" and "main" are Bengaluru words.

## Before any of this

Consent copy reviewed by someone qualified, an agreement covering what the speech provider retains, native review of the launch languages, and the instrumentation built and tested to carry no address data.
