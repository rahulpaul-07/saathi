"""Interface text for the room pages, in all 10 languages.

Every visible string on the customer and rider pages has an id here. English is the source; the
other nine languages are machine output from `scripts/gen_chrome.py` (local IndicTrans2) kept in
`chrome_data.py`, and each text carries a review status per string, as the quick replies do:
"pending" means no speaker has checked that exact text and the UI says so. Strings contain no
placeholders: the browser joins pieces (`Sent` + `:` + a label) so a translation can never lose or
corrupt a value. Nothing here is personal data.
"""

from saathi.chrome_data import TRANSLATED
from saathi.quickreplies import Phrase

SOURCE = "en"

ENGLISH: dict[str, str] = {
    # Page structure
    "role_customer": "Customer",
    "role_rider": "Rider",
    "back": "Back",
    "demo_banner": "Demo mode: this screen can send prepared clips instead of live speech.",
    "start_a_room": "Start a room",
    "join_a_room": "Join a room",
    "room": "Room",
    "your_language": "Your language",
    "choose_a_language": "Choose a language",
    "create_room": "Create room",
    "room_code": "Room code",
    "join_and_sound": "Join and turn on sound",
    "give_code_to_rider": "Room code. Give it to the rider.",
    "rider_link": "Rider link",
    "reconnecting": "Reconnecting...",
    "waiting_for_rider": "Waiting for the rider to join.",
    "waiting_for_customer": "Waiting for the customer.",
    "waiting_for_directions": "Waiting for directions.",
    "delivery_card": "Delivery card",
    "card_empty_customer": "No address details yet. They collect here as you speak.",
    "card_empty_rider": "No address details yet.",
    "key_facts": "Key facts",
    # Speaking
    "tap_and_speak": "Tap and speak the directions",
    "tap_to_stop": "Tap to stop and send",
    "use_when_stopped": "Use when stopped: tap and speak",
    "ready": "Ready.",
    "try_again": "Try again",
    "discard_recording": "Discard recording",
    "recording": "Recording. Tap again when you are done (60 s maximum).",
    "preparing_audio": "Preparing audio...",
    "sending": "Sending...",
    "recording_discarded": "Recording discarded. Ready.",
    # Demo clips
    "demo_clip": "Demo clip",
    "demo_clip_in_language": "Demo clip in your language",
    "send_demo_clip": "Send demo clip",
    "demo_badge": "Demo clip, not live speech",
    "loading_demo_clip": "Loading demo clip...",
    "demo_clip_failed": "Could not load the demo clip.",
    # What I sent
    "sees_rider": "What the rider sees",
    "sees_customer": "What the customer sees",
    "nothing_sent": "Nothing sent yet.",
    "sent_card_has_details": "Sent. The delivery card has the details.",
    "sent_rider_has_details": "Sent. The rider has these details.",
    "sent_customer_has_details": "Sent. The customer has these details.",
    "sent_demo_rider_has_details": "Sent demo clip. The rider has these details.",
    "sent_demo_customer_has_details": "Sent demo clip. The customer has these details.",
    "sent_check_translation": "Sent, but check the translation.",
    "sent_demo_check_translation": "Sent demo clip, but check the translation.",
    "sent": "Sent",
    "time_taken": "Time taken by your last message",
    "time_stt": "Speech to text",
    "time_translate": "Translation",
    "time_tts": "Text to speech",
    "time_total": "Server total",
    # Quick replies
    "replies_to_rider": "Quick replies to the rider",
    "reply_to_customer": "Reply to the customer",
    "speak_to_customer": "Speak to the customer",
    "quick_replies_failed": "Quick replies could not be loaded.",
    "quick_replies_unavailable": "Quick replies are not available in the other person's language.",
    # What I received
    "from_rider": "From the rider",
    "nothing_received": "Nothing received yet.",
    "repeat": "Repeat",
    "play_again": "Play again",
    "rider_says": "Rider says",
    "customer_says": "Customer says",
    "quick_reply_from_rider": "Quick reply from the rider",
    "quick_reply_from_customer": "Quick reply from the customer",
    "new_message_rider": "New message from the rider.",
    "new_message_customer": "New message from the customer.",
    "last_message_rider": "Last message from the rider.",
    "last_message_customer": "Last message from the customer.",
    "translation_unchecked": "The translation could not be fully checked; trust the facts above.",
    "audio_failed": "Could not load the audio. The facts above are still correct.",
    "tap_repeat": "Tap Repeat to hear it.",
    "tap_repeat_each": "Tap Repeat to hear each message.",
    "unreviewed_translation": "Unreviewed machine translation.",
    "labels_unreviewed": "Some labels are unreviewed machine spellings.",
    "landmark_machine": "The landmark is machine-translated; the original is in brackets.",
    "end_room": "End room",
    # The other person
    "rider_joined": "The rider joined.",
    "customer_joined": "The customer joined.",
    "their_language": "Their language",
    # Chips
    "could_be": "could be",
    "check_this": "check this",
    "changed_was": "changed, was",
    "confirm": "Confirm",
    "confirmed": "confirmed",
    # Room lifecycle and errors
    "enter_code": "Enter the 6-character room code.",
    "room_ended": "The room has ended.",
    "room_expired_rider": "The room has expired. Ask for a new code.",
    "room_expired_customer": "The room has expired. Start a new one.",
    "language_list_failed": "Could not load the language list. Reload the page.",
    "no_connection": "No connection to the server. Check the network and try again.",
    "room_not_found": "Room not found or it has expired. Check the code.",
    "wait_or_full": "Waiting for the other person to join, or the room is full.",
    "not_allowed": "That action is not allowed here.",
    "still_busy": "Still busy. Try again.",
    "too_many_turns": "Too many turns, wait a moment, then try again.",
    "speech_unavailable": "The speech service is unavailable. Try again.",
    "no_speech": "Didn't catch that, please try again.",
    "unreliable": "I couldn't translate that reliably. Please try again.",
    "bad_recording": "That recording can't be used. Please record again.",
    "i_heard": "I heard",
    "mic_secure_page": "The microphone needs a secure page (HTTPS or localhost).",
    "mic_not_found": "No microphone was found.",
    "mic_blocked": (
        "Microphone access was blocked. Allow it in the browser's site settings, then try again."
    ),
    "recording_unreadable": "This browser could not read the recording. Please try again.",
    # Shown on pages whose language is machine-translated and not yet reviewed
    "chrome_unreviewed": "The text on this page is machine-translated and not yet reviewed.",
}

CHROME: dict[str, dict[str, Phrase]] = {
    SOURCE: {key: Phrase(text, "source") for key, text in ENGLISH.items()},
    **{
        code: {key: Phrase(text, status) for key, (text, status) in strings.items()}
        for code, strings in TRANSLATED.items()
    },
}


def word_overlap(source: str, other: str) -> float:
    """Share of the source's words found in `other`, 0 to 1: a cheap drift check for a
    back-translation. It is a flag for a human to look at, never a quality score."""
    words = [w for w in source.lower().replace("...", " ").split() if w.strip(".,:;?!()")]
    found = set(other.lower().replace("...", " ").split())
    cleaned = [w.strip(".,:;?!()") for w in words]
    hits = sum(1 for w in cleaned if w in {f.strip(".,:;?!()") for f in found})
    return hits / len(cleaned) if cleaned else 1.0
