from saathi.card import Card
from saathi.facts import Fact, FactKind


def fact(kind: FactKind, value: str) -> Fact:
    return Fact(kind=kind, value=value, start=0, end=1, heard=value, confidence="high")


def values(card: Card) -> dict[str, str]:
    return {kind: entry.fact.value for kind, entry in card.entries.items()}


def test_a_new_value_is_added_without_a_marker() -> None:
    card = Card()
    card.update([fact("gate", "2"), fact("floor", "3")])
    assert values(card) == {"gate": "2", "floor": "3"}
    assert all(entry.previous is None for entry in card.entries.values())


def test_a_changed_value_keeps_the_old_one_in_the_marker() -> None:
    card = Card()
    card.update([fact("gate", "2"), fact("floor", "3")])
    card.update([fact("gate", "4")])
    assert values(card) == {"gate": "4", "floor": "3"}
    assert card.entries["gate"].previous == "2"
    assert card.entries["floor"].previous is None


def test_the_marker_clears_on_the_next_turn_with_facts() -> None:
    card = Card()
    card.update([fact("gate", "2")])
    card.update([fact("gate", "4")])
    card.update([fact("floor", "1")])
    assert card.entries["gate"].previous is None
    assert values(card) == {"gate": "4", "floor": "1"}


def test_the_same_value_repeated_is_not_a_change() -> None:
    card = Card()
    card.update([fact("gate", "2")])
    card.update([fact("gate", "2")])
    assert card.entries["gate"].previous is None


def test_a_turn_without_facts_changes_nothing_and_keeps_markers() -> None:
    card = Card()
    card.update([fact("gate", "2")])
    card.update([fact("gate", "4")])
    card.update([])
    assert card.entries["gate"].previous == "2"


def test_within_one_turn_the_last_fact_of_a_kind_wins() -> None:
    card = Card()
    card.update([fact("gate", "2"), fact("gate", "5")])
    assert values(card) == {"gate": "5"}
    assert card.entries["gate"].previous is None


def test_entries_follow_the_fixed_kind_order() -> None:
    card = Card()
    card.update([fact("landmark", "temple"), fact("floor", "3"), fact("gate", "2")])
    assert list(card.entries) == ["gate", "floor", "landmark"]


def test_clear_drops_everything() -> None:
    card = Card()
    card.update([fact("gate", "2")])
    card.clear()
    assert card.entries == {}
