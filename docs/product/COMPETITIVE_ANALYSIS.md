# Saathi: competitive analysis

Date: 13 Nov 2026. Based on one round of web research, not hands-on testing of each product. Claims about other products come from the linked sources and should be re-checked before being quoted. Where I found nothing, the cell says so; that is not proof the feature does not exist.

## The real competitor is the phone call

Today a rider who cannot follow directions calls the customer through the platform's masked number, asks a passer-by or the security guard, or works from the map pin. Any product here competes first with that habit, which costs nothing and needs no new screen. Whether the habit fails often enough to matter is the open question in the PRD.

## Substitutes

| Product | What it does | Strength against Saathi | Gap for this job |
|---|---|---|---|
| Google Translate, Live translate | Two-way spoken conversation with audio and an on-screen transcript in both languages, more than 70 languages including Hindi, Tamil, Kannada, Telugu and Marathi. Available in India. On Android it can run in the background with the screen locked. | Free, already installed, far better models, hands-free, many more languages | A transcript, not structured facts. Nothing marks a changed gate number or lets the rider confirm one value. Both people must be at one phone or on a call with it. Not tested on code-mixed directions by me. |
| Bhashini app (Government of India) | Text, voice and a "Converse" mode between Indian languages. Text covers 22 languages; the source I found lists Converse at 13. | Public, free, covers languages Saathi does not (Odia, Assamese, Urdu) | Same as above: general conversation, no address structure. |
| Samsung interpreter | On-device interpreter on Galaxy phones | Works offline, no extra app on those phones | Device-limited. Not researched further here. |
| Swiggy with Sarvam AI | Voice ordering in 11 Indian languages across food delivery, Instamart and Dineout, announced March 2026 | Shows the platforms are investing in Indian-language voice, and have a speech partner | This is customer to app, for placing orders. I found no rider-to-customer translation feature. |
| Zomato regional-language app | App interface in Hindi and other regional languages | Reduces the language gap between the customer and the app | Interface only. I found no rider-to-customer translation feature. |
| Platform masked calling and chat | Rider and customer talk or type through the app | Zero friction, already the habit | No translation that I found. |

## Positioning

General interpreters optimise for a fluent sentence. Saathi optimises for seven address facts arriving intact and being acknowledged. Its differences are narrow and specific:

1. Tiles come from the speaker's own words, so a wrong translation cannot corrupt them.
2. A corrected value is marked "changed, was X" until the rider confirms it.
3. The rider can confirm or question one fact with one tap and no speech.
4. Nothing is stored after the conversation.

## Honest assessment

- **The moat is thin.** Rule-based extraction and a card are easy for a platform or for Google to copy. The durable parts would be distribution through a delivery partner and evaluation data from real deliveries, and Saathi has neither.
- **A stronger general model may make the core bet unnecessary.** If a current live-translation model rarely drops a gate number in code-mixed speech, the structured card is a nice-to-have. That comparison has not been run. It should be: the same 50 demo clips through Google's Live translate, scored with the same fact check.
- **The platforms are the likely builders.** Swiggy already has a speech partner. The realistic outcome of a good pilot is a feature inside a platform's rider app, not a standalone product.
- **Where Saathi could still win.** As a demonstration that the confirmable-facts pattern lowers wrong-gate deliveries, with numbers a platform cannot get from a general interpreter.

## What would change this analysis

| Evidence | Effect |
|---|---|
| Riders say directions in another language are a weekly problem | Supports building further |
| Riders say the call or the guard always sorts it out | Stop |
| Live translate keeps all facts on the 50 clips | The card must justify itself on confirmation and correction alone |
| A platform ships rider-to-customer translation | Reposition as an evaluation method, or stop |

## Sources

- [Google: live translation and language learning tools in Translate](https://blog.google/products-and-platforms/products/translate/language-learning-live-translate/)
- [Deccan Herald: Translate live translation supports Kannada, Hindi and 70 plus languages](https://www.deccanherald.com/amp/story/technology%2Fartificial-intelligence%2Fgoogle-translate-app-gets-ai-powered-real-time-translation-feature-supports-kannada-hindi-70-plus-languages-3699331)
- [India.com: Live translate background processing on Android](https://www.india.com/technology/google-translate-rolls-out-real-time-two-way-translation-hands-free-features-check-out-how-it-works-8517623/)
- [Vikaspedia: Bhashini app features](https://en.vikaspedia.in/viewcontent/e-governance/digital-india/bhashini?lgn=en)
- [YourStory: Swiggy partners with Sarvam for voice-led multilingual services](https://yourstory.com/2026/03/swiggy-partners-with-sarvam-for-voice-led-multi-lingual-services)
- [Free Press Journal: Swiggy voice ordering in 11 Indian languages](https://www.freepressjournal.in/tech/swiggy-partners-with-sarvam-ai-to-bring-voice-ordering-in-11-indian-languages-how-does-it-work)
- [Inc42: Zomato app in Hindi and regional languages](https://inc42.com/buzz/zomato-app-now-available-in-hindi-startup-delivers-150k-orders-a-month-via-regional-languages/amp)
