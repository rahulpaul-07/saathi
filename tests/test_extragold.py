"""The held-out gold for ta, te, gu, ml, mr and pa, and the spellings its first run added."""

import pytest

from saathi.evaluation.extragold import LANGS, as_probe, gold_set, planned_calls
from saathi.evaluation.factscore import score_transcript
from saathi.evaluation.lexprobe import ROUND2_LANGS
from saathi.facts import extract_facts


def test_four_sentences_per_language_with_unique_ids() -> None:
    gold = gold_set()
    assert len(gold) == 4 * len(LANGS)
    assert len({g.id for g in gold}) == len(gold)
    assert {g.lang for g in gold} == set(LANGS)
    assert set(ROUND2_LANGS) < set(LANGS)


def test_planned_calls_is_two_per_sentence_and_probe_view_keeps_text() -> None:
    gold = gold_set()
    assert planned_calls(gold) == 48
    probes = [(p.id, p.lang, p.text) for p in as_probe(gold)]
    assert probes == [(g.id, g.lang, g.text) for g in gold]


def test_gold_facts_match_the_spoken_templates() -> None:
    first = gold_set(("gu",))[0]
    wanted = [("cross", "7"), ("main", "3"), ("gate", "12")]
    assert [(f.kind, f.value) for f in first.facts] == wanted
    assert score_transcript(first, "").all_correct == 0  # silence finds none of them


# Spellings the STT wrote for these sentences that the lexicon did not have (x-ta-3, x-te-1,
# x-te-2, x-ml-2, x-pa-1). Machine-verified, not native-reviewed.
@pytest.mark.parametrize(
    ("lang", "heard", "kind", "value"),
    [
        ("ta", "பதின்மூன்றாவது கிராஸ்", "cross", "13"),
        ("te", "ఏడో క్రాస్", "cross", "7"),
        ("te", "తొమ్మిదో ఫ్లోర్", "floor", "9"),
        ("ml", "ഒമ്പതാം ഫ്ലോർ", "floor", "9"),
        ("pa", "ਗੇਟ ਨੰਬਰ ਬਾਰ੍ਹਾਂ", "gate", "12"),
    ],
)
def test_spelling_added_after_the_held_out_run(
    lang: str, heard: str, kind: str, value: str
) -> None:
    facts = extract_facts(heard, lang)
    assert [(f.kind, f.value, f.ambiguous) for f in facts] == [(kind, value, False)]
