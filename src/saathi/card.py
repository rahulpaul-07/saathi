"""The delivery card: the latest known value of each address fact, merged across customer turns.

It lives only on its Room, in memory. It is dropped with the room (close, idle or hard TTL) and is
never logged or written to disk. Only the customer's turns update it; a rider's facts are shown for
that turn only. See docs/DESIGN.md and docs/THREAT_MODEL.md.

A "changed" marker means: a customer turn replaced this value, and `previous` is the value it
replaced. It stays until the listener confirms the entry; a newer value for the kind sets it again
and clears that kind's confirmation. The listener can also ask about an entry (`asked`); asking and
confirming are mutually exclusive and neither is touched by turns that leave the value alone.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from saathi.facts import FACT_KINDS, Fact, FactKind

ChipAction = Literal["confirm", "ask"]


@dataclass(frozen=True)
class CardEntry:
    fact: Fact
    previous: str | None = None  # the value this one replaced, until the listener confirms
    confirmed: bool = False
    # The replaced landmark's name in the listener's language, taken from the fact it came from
    # (translated when that turn ran), so the marker needs no second translation.
    previous_local: str | None = None
    asked: bool = False  # the listener asked about this value and has not confirmed since


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
                    merged[kind] = old
            elif old is not None and old.fact.value == new.value:
                merged[kind] = replace(old, fact=new)  # same value: nothing to re-confirm
            elif old is not None:
                merged[kind] = CardEntry(
                    new, previous=old.fact.value, previous_local=old.fact.local
                )
            else:
                merged[kind] = CardEntry(new)
        self.entries = merged

    def respond(self, kind: FactKind, action: ChipAction) -> bool:
        """Record the listener's answer for one entry. False when the kind is not on the card."""
        entry = self.entries.get(kind)
        if entry is None:
            return False
        if action == "confirm":
            self.entries[kind] = replace(
                entry, previous=None, previous_local=None, confirmed=True, asked=False
            )
        else:
            self.entries[kind] = replace(entry, confirmed=False, asked=True)
        return True

    def clear(self) -> None:
        self.entries.clear()
