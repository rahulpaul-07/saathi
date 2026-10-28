from saathi.languages import EVALUATED_LANGUAGES, LANGUAGES


def test_table_covers_the_ten_gnani_languages_with_unique_codes() -> None:
    assert set(LANGUAGES) == {"bn", "en", "gu", "hi", "kn", "ml", "mr", "pa", "ta", "te"}
    for field in ("gnani_code", "indictrans_code", "tts_voice"):
        values = [getattr(language, field) for language in LANGUAGES.values()]
        assert len(set(values)) == len(values), field


def test_tiers_match_the_design() -> None:
    by_tier = {
        tier: {key for key, lang in LANGUAGES.items() if lang.tier == tier}
        for tier in ("core", "reviewed", "beta")
    }
    assert by_tier["core"] == {"kn", "en", "hi", "bn"}
    assert by_tier["reviewed"] == {"te"}
    assert by_tier["beta"] == {"gu", "ml", "mr", "pa", "ta"}


def test_translation_evaluation_languages_are_in_the_table() -> None:
    assert set(EVALUATED_LANGUAGES) <= set(LANGUAGES)
