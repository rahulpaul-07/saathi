# LAN two-phone check (author runs this; not yet run on the app)

Goal: customer phone speaks, rider phone shows chips and plays loud, translated audio (and the
reverse when the rider speaks), on the
network the street demo will use. Both phones are Android (Chrome). Real Gnani calls spend credits,
so keep it to a handful of turns. Synthetic addresses only.

## Why the Chrome flag
`getUserMedia` (the microphone) only exists in secure contexts. `http://localhost` counts as
secure; `http://<laptop-ip>:8000` does not, so Chrome hides the microphone there. The Android Chrome
flag `unsafely-treat-insecure-origin-as-secure` marks one exact origin as secure. This was shown to
work on 2026-10-06 over the author's phone hotspot (Wi-Fi profile Private, firewall rule for TCP 8000
on Private only). `adb reverse` is not used: it needs a USB cable, which is useless in the street.
Either phone can record (the rider screen has a secondary talk button), so set the flag on both.
Which languages each phone uses is free; pick any two different ones.

## Before you start
- [ ] Laptop on AC power, models warm (the first request after start is slow).
- [ ] `GNANI_API_KEY` set in your own `.env` (never paste it anywhere).
- [ ] Phone hotspot on. Laptop and the other phone join it. The hotspot phone is one of the two
      Saathi phones; it can still open the laptop's address over its own hotspot. Client isolation
      (guest-style networks) would block phone-to-laptop traffic; the author's hotspot does not.

## 1. Network profile and firewall (admin PowerShell)
- [ ] The hotspot Wi-Fi must be classed **Private**: Settings > Network & internet > Wi-Fi >
      the hotspot > Network profile type > Private. Never open the port on Public.
- [ ] Add the rule for Private only:
      `New-NetFirewallRule -DisplayName "Saathi 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Profile Private -Action Allow`

## 2. Host binding
Default uvicorn binds 127.0.0.1, which phones cannot reach. Bind all interfaces:

    uv run --no-sync uvicorn saathi.app:create_app --factory --host 0.0.0.0 --port 8000

Find the laptop address with `ipconfig` (IPv4 of the Wi-Fi adapter on the hotspot). It changes
with every hotspot session, so redo step 3 when it does. LAN only; no tunnel (AGENTS.md out of
scope).

## 3. Chrome flag on each phone
- [ ] Open `chrome://flags/#unsafely-treat-insecure-origin-as-secure`.
- [ ] In the text box type the exact origin `http://<laptop-ip>:8000` (no trailing path), set to
      Enabled, tap Relaunch.
- [ ] Sanity check in that phone's Chrome: `http://<laptop-ip>:8000/languages` returns JSON.

## 4. Run
- [ ] Customer phone: open `http://<laptop-ip>:8000/customer.html`, pick any language, Create room,
      allow the microphone prompt (it must appear; if it does not, the flag is not applied).
- [ ] Rider phone: open `http://<laptop-ip>:8000/rider.html`, pick a different language, enter the
      code, Join (this tap unlocks audio).
- [ ] Customer speaks a synthetic address ("gate number 2, third floor, near the blue temple").
- [ ] Rider sees chips (gate, floor, landmark) and hears the translation without touching the phone.
- [ ] Outdoors, at arm's length, in street noise: audible without maxing the phone volume
      (loudness normalization targets about -18 dBFS RMS, peaks under -1 dBFS).
- [ ] Repeat replays without a new network call; a quick reply from either phone reaches the other
      as text and audio, in the receiver's language.
- [ ] The rider taps the secondary talk button and speaks; the customer phone shows chips and plays
      the translation.
- [ ] Note timings from the server log (stt/translate/tts/total) and any console errors.
- [ ] End room on the customer phone; confirm the rider is told the room closed.

## 5. Cleanup afterwards
- [ ] Stop uvicorn (Ctrl+C). Rooms live only in memory, so they are gone.
- [ ] On each phone: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, delete the origin
      text, set to Default, Relaunch. Leaving it on weakens secure-context protection for that origin.
- [ ] Laptop (admin PowerShell): `Remove-NetFirewallRule -DisplayName "Saathi 8000"`.
- [ ] Set the hotspot network profile back to Public if it was Public before (Settings > Network).
- [ ] Turn the hotspot off; forget the network on the laptop if it was only for this test.

## Record
Phone models and Chrome versions, total turn latency, anything unclear or clipped in the audio.
Not verified on an iPhone: Safari has no equivalent flag, so an iPhone can be a rider only if the
page loads over plain HTTP; its audio unlock behaviour is untested.
