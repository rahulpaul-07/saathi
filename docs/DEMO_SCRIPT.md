# Demo script (draft, about 3 minutes)

Recorded on the LAN setup in `docs/LAN_CHECK.md`: two Android phones, laptop running the server,
street noise in the background if filming outdoors. Only synthetic addresses are spoken. Nothing
below is rehearsed yet; timings are targets, not measurements.

## Before filming
- Server running with models warm (one throwaway turn first).
- Customer phone on `/customer.html`, rider phone on `/rider.html`, flags set, volume at a normal
  level (not maxed).
- Screen recording on the rider phone; a second camera or the laptop on the customer.
- Languages and casting are TBD: roles are not tied to languages, so the customer and the rider can
  each use any of the 10. Pick the pair from who is available to speak on the day and from what
  `docs/EVAL.md` supports. Below, "the customer's language" and "the rider's language" stand for
  whichever pair is chosen; have a second pair ready for another take.

## Script

1. Problem (15 s, voiceover, no demo). A delivery rider is on a bike, the customer is explaining the
   gate and floor in a language the rider does not speak, and every second of misunderstanding costs
   a call back. The numbers matter most: gate 2 versus gate 12.

2. Join (20 s). Customer phone: pick the customer's language, Create room, show the 6-character
   code. Rider phone: pick the rider's language, type the code, tap Join. Say: "Joining needs a tap because phones block autoplay
   until you touch the page."

3. First turn (40 s). Customer taps talk and says the synthetic address: second cross, third main,
   gate number two, opposite the Ganesha temple. Show the rider phone: chips appear first (cross 2,
   main 3, gate 2, landmark), then the translated audio plays on its own. Point at the chips: "The
   chips come from the original transcript, so the numbers do not depend on the translation."

4. Repeat (10 s). Tap Repeat: it replays instantly. Say: "No network call, the audio is already
   on the phone."

5. Quick reply (30 s). Rider taps "Which floor?". The customer phone shows it and plays it in the
   customer's language. Customer answers by voice: third floor, flat 304. New chips appear. Say:
   "The rider never has to speak or type; the three quick replies cover what they actually need.
   The customer has three too, for example 'Come to the gate'." Mention they are
   machine-translated and marked unreviewed (except the phrases the author reviewed). If the rider
   is stopped, they can also answer by voice with the secondary talk button.

6. Hard case (30 s, optional, only if it really works on the day). Customer says a digit-by-digit
   flat number. Show the chip displaying the value as heard with a low-confidence marker. Say:
   "When the recognizer's output is ambiguous, the app shows what it heard instead of guessing."

7. Privacy and limits (20 s, voiceover). Rooms expire and live in memory, transcripts are never
   stored, addresses in this demo are invented. Beta languages are labelled. This is a LAN prototype,
   not a deployed service.

8. Evaluation (15 s, voiceover, ONLY after results exist). State the critical-fact precision and
   recall with their confidence intervals from `docs/EVAL.md`, on clean speech and at 20/10/5 dB
   street noise. Do not say anything about accuracy before those numbers exist.

## Do not claim
- Any accuracy number not in `docs/EVAL.md`.
- That Odia, Assamese or Urdu work, or that beta languages are verified.
- That iPhone riders work (untested).
- Safety while riding: the product is meant for a stop or when pulled over.
