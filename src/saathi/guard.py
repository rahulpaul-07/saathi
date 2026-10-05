"""Output sanity check: detect the looping text a translation model emits when it degenerates."""

import string

MAX_PHRASE_WORDS = 3
MIN_REPEATS = 4  # "না না না" (3) is natural emphasis; four consecutive repeats is a loop

_EDGE_PUNCTUATION = string.punctuation + "।॥…“”‘’"


def _words(text: str) -> list[str]:
    stripped = (word.strip(_EDGE_PUNCTUATION) for word in text.split())
    return [word for word in stripped if word]


def has_repeated_phrase(text: str) -> bool:
    """True if a phrase of 1 to 3 words occurs 4 or more times back to back."""
    words = _words(text)
    for size in range(1, MAX_PHRASE_WORDS + 1):
        # A phrase of `size` words repeated N times is (N - 1) * size consecutive positions where
        # a word equals the one `size` places before it.
        matches = 0
        for i in range(size, len(words)):
            matches = matches + 1 if words[i] == words[i - size] else 0
            if matches >= (MIN_REPEATS - 1) * size:
                return True
    return False
