# Demo script (about 3 minutes, no people on screen)

No person speaks or appears. Every voice is Gnani TTS or FLEURS public speech data, sent as
prepared clips in demo input mode, with licensed street noise mixed in at 10 dB. Only invented
addresses are used. Timings are targets, not measurements; nothing has been filmed yet.

## Setup (once)

1. `uv run --no-sync python scripts/fetch_noise.py` (street noise, pinned).
2. After the author approves the Gnani budget: `scripts/make_demo_clips.py --dry-run`, then the real
   run. It writes `demo/clips/` (gitignored): `kn-wrong-translation`, `kn-bakery`, `ta-gate`,
   `te-gate`.
3. Start the server with `SAATHI_DEMO_INPUT=1` and open `http://127.0.0.1:8000/demo.html` in a
   1920x1080 window (the stage keeps 16:9). Customer is on the left, rider on the right; the room
   code is copied across for you. Record the window.
4. Warm up with one throwaway turn so models are loaded.

On screen, demo mode shows a "Demo mode" banner, and every clip carries a "Demo clip, not live
speech" badge on both screens. Do not hide them.

Pairs used (an example casting; roles are not tied to languages): kn to hi, ta to hi, te to en.
The rider speaks Hindi in every shot of the main flow (shots 2 to 7); there is no Bengali rider in
the video. The wrong-translation stills in shot 7 were regenerated for a Hindi rider.

## Calls and the ledger

The live server uses the plain Gnani client, so its calls are not in the ledger. A full take is
10 calls (shot 3: 2, shot 5: 1, shot 6: 1, shot 7: 2, shot 8: 4; Repeat is free), 8 when the two
quick-reply phrases are already cached by the running server. After the session, count the calls
and log them by hand:

    uv run --no-sync python scripts/log_demo_calls.py 42 --label demo-live

It refuses a count that would pass the cap.

## Shot list

| # | Shot | Screen action | Caption |
|---|---|---|---|
| 1 | Problem, 15 s | Title card | "The rider needs gate 2, not gate 12." |
| 2 | Join, 20 s | Customer: Kannada, Create room. Rider: Hindi, Join (code already filled) | "A short-lived room. Nothing is stored." |
| 3 | First turn, 35 s | Customer: pick "Gate 4, bakery", Send demo clip. Chips appear on the rider, then audio | "Chips come from the original transcript, not from the translation." |
| 4 | Repeat, 10 s | Rider: Repeat | "Replays instantly from the phone." |
| 5 | Quick reply rider to customer, 20 s | Rider taps a quick reply; the customer sees it in Kannada | "Three quick replies per role, in all 10 languages. Review status is shown." Kannada phrases are machine translations, not yet reviewed: the screen says so, and the caption must not call them checked. |
| 6 | Quick reply customer to rider, 15 s | Customer taps a quick reply; the rider sees it in Hindi (author-reviewed) | "Either side can reply without speaking." |
| 7 | Wrong translation, 40 s | Customer: "Gate 2, Ganesha temple", Send demo clip. Insert card: `docs/media/rider-unmasked.png` next to `rider-masked.png`, then back to the live chips | "Fluent but wrong translation. The chips are still correct." |
| 8 | Other pairs, 30 s | New rooms: ta to hi with "Gate 3, bakery"; te to en with "Gate 1, Hanuman temple" | "Any of the 10 languages can be either role." |
| 9 | Privacy and limits, 15 s | Voiceover over the room screen | "Rooms expire. Transcripts are never stored. Beta languages are labelled." |
| 10 | Evaluation, 15 s | ONLY after results exist: table from `docs/EVAL.md` | Numbers with their confidence intervals, and the audio-source label next to each |
| 11 | End card | Credits | "Voices: Gnani TTS and FLEURS public speech data, mixed with a licensed street-noise recording." |

The insert card in shot 7 is a labelled still, not live output: caption it "Recorded earlier, same
input, translation masking off and on".

What the shot 7 stills show (local IndicTrans2, kn to hi, checked with `scripts/check_kn_hi.py`):
unmasked, the Hindi reads "third main gate, number two ... opposition's Ganesha temple" (main road
became "main gate", "opposite" became "opposition"); the numbers are still right. Masked, the
sentence keeps "2 cross, 3 main, gate number 2, opposite Ganesha temple". The placeholder check
passes for this clip, so the fallback fact summary does NOT fire here: do not caption it as such.
The chips are identical in both stills.
Shot 7 voiceover line: "Even the masked sentence, '3 मेन गेट नंबर 2', can be misread, which is why the chips (main 3, gate 2) are the source of truth."

## Credits (end card, verbatim)

Voices: Gnani TTS and FLEURS public speech data, mixed with a licensed street-noise recording.

Add below it, in small type: FLEURS: Google, CC BY 4.0. Street noise: "College Street" by
Calcuttan, Freesound 181026, CC BY 4.0.

## Do not claim
- Any accuracy number not in `docs/EVAL.md`, or any figure without its audio-source label
  (clean synthetic, or real human speech from FLEURS).
- That the demo clips are live speech or real speakers.
- That Odia, Assamese or Urdu work, or that beta languages are verified.
- That iPhone riders work (untested).
- Safety while riding: the product is meant for a stop or when pulled over.
