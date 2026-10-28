# Recording script: Rahul (en, hi, bn) and street noise

20 utterances (12 en, 4 hi, 4 bn), numbered to match `eval/gold/directions.json`. The Kannada ones
(g02, g06, ...) are for the friends: `kannada_script.md`. All addresses are invented. Recordings are
"consented human speech", stay in `eval/audio/` (gitignored) and are never committed.

## How to record

1. Phone voice recorder app, quiet room, phone about 20 cm from your mouth, one file per line.
2. Press record, wait about one second, read the line at normal speaking pace the way you would
   say it to a rider on the phone, stop. Do not read punctuation aloud. If you stumble, record the
   line again and keep only the good take (a stumble counts as an STT error in the results).
3. Say numbers naturally. If the line shows digits (402, 1205), say them the way you would say
   them aloud; do not spell them out unless the line does. Read lines exactly as written otherwise:
   g13 has "1/4 floor" (say "one slash four floor"), g25 and g29 spell their numbers out.
4. Name each file `<id>.<ext>` (for example `g01.m4a`) and copy them all to a folder such as
   `C:\PROJECTS\saathi\eval\audio\raw\`.
5. Convert to 16 kHz mono 16-bit WAV (needs ffmpeg, already installed):

       uv run --no-sync python scripts/convert_recording.py --batch eval/audio/raw eval/audio/gold

   This writes `eval/audio/gold/g01.wav` and so on, and validates each file. The noise evaluation
   reads exactly these names. Do not edit or trim the files further.

## Your lines

English
- g01: Second cross, third main, gate number 2, opposite the Ganesha temple.
- g03: Block C, flat 402, fourth floor, near the blue building.
- g05: Take the 2nd cross and then 5th main, gate 3 is next to the bakery.
- g08: I am in tower B, flat 1205, 12th floor, near the water tank
- g09: Gate number two, third floor, flat 304, opposite the petrol bunk.
- g13: Flat 12, 1/4 floor, gate 1, behind the school.
- g17: House number 14, 3rd cross, 2nd main, near the green gate
- g20: Flat 5B, second floor, gate number 4, behind the cycle shop.
- g21: Our house is the one with the red door, 3rd main, 7th cross.
- g25: Gate twenty one, first floor, flat one zero two, near the mango tree.
- g27: Tower A, flat 1101, eleventh floor, gate 5, opposite the pharmacy.
- g29: Ground floor, flat two hundred and four, gate number 1, beside the temple road.

Hindi
- g04: दूसरे क्रॉस और तीसरे मेन पर गेट नंबर दो, गणेश मंदिर के सामने।
- g11: ब्लॉक सी, फ्लैट तीन सौ चार, चौथी मंजिल, नीली बिल्डिंग के पास
- g15: पांचवीं मंजिल, फ्लैट 502, गेट नंबर 3, पेट्रोल पंप के सामने
- g23: टावर बी, फ्लैट एक चार दो, सेकंड फ्लोर, स्कूल के पीछे

Bengali
- g07: দুই নম্বর ক্রস, তিন নম্বর মেইন, গেট নম্বর দুই, গণেশ মন্দিরের সামনে
- g14: ফ্ল্যাট ৩০৪, তৃতীয় তলা, ব্লক সি, নীল বিল্ডিংয়ের পাশে
- g18: গেট নম্বর ৪, পাঁচ তলা, ফ্ল্যাট পাঁচ বি, স্কুলের পেছনে
- g26: চার নম্বর গেট, দ্বিতীয় তলা, ফ্ল্যাট একশো দুই, মন্দিরের কাছে

Checklist: 20 files in `eval/audio/gold/` named g01, g03, g04, g05, g07, g08, g09, g11, g13, g14,
g15, g17, g18, g20, g21, g23, g25, g26, g27, g29 (`.wav`). Dev utterances (id divisible by 3:
g03, g09, g15, g18, g21, g27) are used to tune; the rest are the frozen test split.

## Street traffic noise (about 60 seconds)

This file is the primary noise for the evaluation (pink noise is only a secondary stressor).

1. Stand on a real street with moving traffic, away from your own voice: no talking, no music,
   no phone notifications (put the phone on silent / airplane mode).
2. Hold the phone the way a rider would hold it, microphone facing the road, about 20 cm from your
   body, same voice recorder app as above. Record 60 to 90 seconds without touching the phone.
3. Avoid wind blasts on the microphone (stand behind a pillar or turn the mic away from the wind),
   a siren or horn that dominates the whole clip, and nearby conversation (it would be speech).
4. Save as `street.<ext>` and convert (this mode allows at least 30 s and no 60 s limit):

       uv run --no-sync python scripts/convert_recording.py --street street.m4a

   It writes `eval/audio/noise/street.wav` (gitignored). The harness picks a seeded random
   segment from it for each clip, so the longer and more varied it is, the better.
5. Note the place and time (for the EVAL.md method section); do not record identifiable people.
