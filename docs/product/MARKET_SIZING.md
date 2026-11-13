# Saathi: market sizing

Date: 13 Nov 2026. This is a sizing method with the known inputs filled in and the unknown ones marked. It does not produce a headline number, because three of the five inputs are unknown and inventing them would make the answer look more certain than it is.

## What is known

| Input | Value | Source and caveat |
|---|---|---|
| Gig and platform workers in India, FY25 | About 12 million | Economic Survey 2025-26, as reported. Covers all gig work, not only delivery. |
| Same, 2020-21 | 7.7 million | NITI Aayog, June 2022 |
| Projection, 2029-30 | 23.5 million | NITI Aayog. A projection, not a measurement. |
| Provider cost per conversation | About 1.5 credits for 6 turns | This repo's model, on assumed turn counts. Rupee price per credit unknown. |

## What is not known

| Input | Why it matters | How to find out |
|---|---|---|
| Share of gig workers who are delivery riders | Sets the user base | Platform annual reports and filings; the 2022 NITI Aayog report's sector split |
| Deliveries per rider per day | Converts riders into conversations | Platform filings, rider interviews |
| Share of deliveries where rider and customer share no working language | The core of the opportunity. Likely concentrated in metros with many migrant riders. | Rider interviews first, then a platform's own data on rider and customer app languages |
| Share of those where directions are needed beyond the map pin | Gated communities and apartment blocks need them; a house on a street may not | Rider interviews, platform call-rate data |
| What a wrong gate costs the platform | Sets willingness to pay | Platform data: minutes lost, failed deliveries, support contacts |

## The model

```
Addressable conversations per day
  = delivery riders
  x deliveries per rider per day
  x share with no shared language
  x share needing spoken directions

Value per conversation
  = (wrong-gate rate without Saathi - wrong-gate rate with Saathi)
  x cost of a wrong gate to the platform

Margin per conversation
  = value captured by price - provider cost - compute cost
```

## How to read it

- The business case does not rest on the size of the gig workforce. It rests on the two shares in the middle of the first formula, and nobody outside the platforms knows them.
- The buyer is a platform, so the market is a handful of customers. Sizing by rider count overstates how many buying decisions exist.
- If the no-shared-language share is small, the product is a feature for a few cities, not a business. That is a fine outcome for a portfolio project and should be said plainly.

## If asked for a number in an interview

Walk the formula aloud, state each assumption as an assumption, and give a range. For example: "About 12 million gig workers; I would assume some fraction are delivery riders and I would say what I assumed; I do not know the cross-language share and would want platform data before trusting any figure." Showing the structure and the unknowns is the skill being tested.

## Sources

- [Outlook Business: what the numbers say about India's gig workers](https://www.outlookbusiness.com/start-up/news/pay-education-demographics-what-the-numbers-say-about-indias-1-crore-gig-workers)
- [Invest India: gig economy to have 23.5 million workers by 2029-30](https://indbiz.gov.in/indias-gig-economy-to-have-23-5-million-workers-by-2029-30-niti-aayog/)
- [Xflow: gig economy India statistics 2026, with source table](https://www.xflowpay.com/blog/gig-economy-india-statistics)
