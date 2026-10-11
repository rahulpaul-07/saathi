"""Do STT errors cluster at the start of a clip? (Phone case 1: Gnani misheard the first words.)"""

from dataclasses import dataclass
from difflib import SequenceMatcher

from saathi.evaluation.metrics import normalize

HEAD_WORDS = 2


@dataclass(frozen=True)
class HeadTail:
    """Reference words missed by the transcript, split into the first words and the rest."""

    head_words: int = 0
    head_missed: int = 0
    tail_words: int = 0
    tail_missed: int = 0

    def __add__(self, other: "HeadTail") -> "HeadTail":
        return HeadTail(
            self.head_words + other.head_words,
            self.head_missed + other.head_missed,
            self.tail_words + other.tail_words,
            self.tail_missed + other.tail_missed,
        )

    @property
    def head_rate(self) -> float:
        return self.head_missed / self.head_words if self.head_words else 0.0

    @property
    def tail_rate(self) -> float:
        return self.tail_missed / self.tail_words if self.tail_words else 0.0


def head_tail_misses(reference: str, hypothesis: str, head: int = HEAD_WORDS) -> HeadTail:
    """Count reference words with no exact match in the transcript, by position in the clip.

    Words are matched with a longest-common-subsequence style alignment, so one dropped word does
    not make every later word count as missed.
    """
    ref = normalize(reference).split()
    hyp = normalize(hypothesis).split()
    matched: set[int] = set()
    for block in SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks():
        matched.update(range(block.a, block.a + block.size))
    head_count = min(head, len(ref))
    head_missed = sum(1 for i in range(head_count) if i not in matched)
    tail_missed = sum(1 for i in range(head_count, len(ref)) if i not in matched)
    return HeadTail(head_count, head_missed, len(ref) - head_count, tail_missed)
