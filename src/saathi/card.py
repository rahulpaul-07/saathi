"""The delivery card: the latest known value of each address fact, merged across customer turns.

It lives only on its Room, in memory. It is dropped with the room (close, idle or hard TTL) and is
never logged or written to disk. Only the customer's turns update it; a rider's facts are shown for
that turn only. See docs/DESIGN.md and docs/THREAT_MODEL.md.

A "changed" marker means: the latest customer turn that carried facts replaced this value, and
`previous` is the value it replaced. The next such turn clears every marker, so a marker never
outlives the update it describes.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from saathi.facts import FACT_KINDS, Fact, FactKind


@dataclass(frozen=True)
class CardEntry:
    fact: Fact
    previous: str | None = None  # the value this one replaced, set only when the value changed


@dataclass
class Card:
    entries: dict[FactKind, CardEntry] = field(default_factory=dict)

    def update(self, facts: Sequence[Fact]) -> None:
        """Merge one customer turn. Within a turn the last fact of a kind wins (a spoken
        correction comes after the mistake). A turn without facts changes nothing."""
        if not facts:
            return
        latest = {fact.kind: fact for fact in facts}
        merged: dict[FactKind, CardEntry] = {}
        for kind in FACT_KINDS:
            old = self.entries.get(kind)
            new = latest.get(kind)
            if new is None:
                if old is not None:
                    merged[kind] = CardEntry(old.fact)  # kept, marker cleared
            elif old is not None and old.fact.value != new.value:
                merged[kind] = CardEntry(new, previous=old.fact.value)
            else:
                merged[kind] = CardEntry(new)
        self.entries = merged

    def clear(self) -> None:
        self.entries.clear()
