# Rider interview guide

Purpose: find out whether delivery riders have the problem Saathi assumes they have, and whether the rider screen works for them. This is research to test the assumptions in `PRD.md` section 9. It is not a sales pitch for Saathi.

Target: 3 to 5 delivery riders. A small number is enough to learn whether the problem is real and what is wrong with the screen. It is not enough to produce statistics, so report counts, not percentages.

## Ground rules

- Talk to people who agree. Explain who you are, what you are doing and that it is for a student project. Make clear they can stop at any time and that nothing they say affects their work.
- Do not record audio or video unless they clearly agree. Take handwritten notes instead.
- Do not collect names, phone numbers, employer or addresses. Label each person Rider 1, Rider 2 and so on, with city and language only.
- Do not interview someone who is mid-delivery. Pick a break, and keep it to 15 to 20 minutes. Offer tea or their time back in some form.
- Ask about what happened, not what they would do. "Tell me about your last delivery where you could not find the address" gives better answers than "would you use an app that translates?"
- Do not describe Saathi until the second half. Hearing about it first changes what they tell you.
- Say clearly if you do not speak their language, and use a translator they are comfortable with.

## Who to find

Riders you can reach without pressure: people you already know, or riders who agree when you ask near your hostel or a delivery pickup point. Ask the person first. Aim for different languages if you can, since the problem is mostly between language groups. Write down how you found each person, because it affects how far you can generalise.

## Part 1: their work today (8 to 10 minutes)

Open with: "I am a student looking at how riders find addresses. I would like to hear how it really goes. There are no right answers."

1. Tell me about the last delivery where it took longer than it should to find the customer.
2. What went wrong? What did you do?
3. How do you usually get the exact gate, floor or landmark? Call, chat, map, ask someone?
4. When the customer speaks a language you do not speak, what happens? Tell me about the last time.
5. Which detail is hardest to get right: gate, floor, cross, main, landmark, flat number? Why?
6. What do you look at on your phone when you arrive?
7. Where are you usually when you make or take that call: moving, stopped, at the gate?
8. How often does a delivery fail or get delayed because of a wrong gate or floor? Do not push for a number; "most days, sometimes, rarely" is fine.

Listen for: how they cope now, how often the language gap really matters, and which facts cause the most trouble. If they say it is not a problem for them, write that down. It is a real finding.

## Part 2: the screen (8 to 10 minutes)

Show the rider screen wireframe (`rider_screen_wireframe.svg`, printed or on your phone). Do not explain it first.

1. Without me saying anything, what do you think this screen is for?
2. If this appeared when you reached the gate, what would you look at first?
3. Show me where you would find the gate. The floor. The landmark.
4. The gate says "changed, was 4". What do you think that means?
5. What would you do with the tick and the question mark?
6. What is missing? What would you remove?
7. Would you look at this, listen to the audio, or call the customer? Why?
8. Would you use this on a real delivery? What would stop you?

Write down what they do as well as what they say: where their eyes go, what they touch, where they hesitate. If they misread something, do not correct them. The misreading is the finding.

## Part 3: close (2 minutes)

- Is there anything about finding addresses that I did not ask and should have?
- Thank them. Do not promise that anything will be built.

## Notes template

Fill one row per person straight after the conversation.

| | Rider 1 | Rider 2 | Rider 3 | Rider 4 | Rider 5 |
|---|---|---|---|---|---|
| City and language | | | | | |
| How I found them | | | | | |
| Last hard delivery, in their words | | | | | |
| How they get gate and floor today | | | | | |
| Language gap: how often and how handled | | | | | |
| Hardest fact | | | | | |
| What they looked at first on the screen | | | | | |
| Misreadings or confusion | | | | | |
| Would they use it, and what blocks them | | | | | |

## Turning notes into findings

1. Read all notes together. Underline anything that appeared with two or more riders.
2. Write findings as "3 of 4 riders said X" or "1 rider did Y". Never write a percentage with this few people.
3. For each assumption in `PRD.md` section 9, mark it supported, contradicted or not enough evidence, and say which riders.
4. Change the PRD and the rider screen where the findings say to. Keep a short list of what you changed and why. That list is the useful output.
5. Record anything that surprised you. Surprises are what a PM interview will ask about.

## What you can and cannot say afterwards

Say only what happened. If you talked to four riders, say four. If three of them said the language gap is rare, say that, even though it weakens the case for Saathi. Reporting a result that disagrees with your own project is more credible than one that does not.

Do not add "user research" to a resume until you have done the interviews and kept the notes. Then it is accurate, and you can answer questions about what you asked, what you heard and what you changed.
