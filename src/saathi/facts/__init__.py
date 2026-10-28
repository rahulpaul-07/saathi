"""Local, rule-based extraction of the critical address facts from a transcript."""

from saathi.facts.extract import MAX_TEXT_CHARS, extract_facts
from saathi.facts.types import FACT_KINDS, Fact, FactKind

__all__ = ["FACT_KINDS", "MAX_TEXT_CHARS", "Fact", "FactKind", "extract_facts"]
