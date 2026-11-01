"""Read-only public data the UI needs: languages, quick replies, interface text, feature flags."""

from collections.abc import Mapping

from fastapi import APIRouter
from pydantic import BaseModel

from saathi.chrome import CHROME
from saathi.language_names import names_of
from saathi.languages import LANGUAGES, Tier
from saathi.quickreplies import IDS_BY_ROLE, QUICK_REPLIES, ReviewStatus
from saathi.rooms import Role


class LanguageOut(BaseModel):
    code: str
    name: str
    native: str
    tier: Tier
    names: dict[str, str]  # this language's name in each viewer's script, keyed by viewer


class PhraseOut(BaseModel):
    text: str
    review_status: ReviewStatus


class QuickReplyTableOut(BaseModel):
    ids: dict[Role, list[str]]  # which phrase ids each role may send
    languages: dict[str, Mapping[str, PhraseOut]]  # language -> phrase id -> phrase


class ChromeTableOut(BaseModel):
    languages: dict[str, Mapping[str, PhraseOut]]  # language -> string id -> text


class FeaturesOut(BaseModel):
    demo_input: bool  # prepared clips may be sent instead of the microphone


def catalog_router(demo_input: bool = False) -> APIRouter:
    router = APIRouter()

    @router.get("/features")
    async def features() -> FeaturesOut:
        return FeaturesOut(demo_input=demo_input)

    @router.get("/languages")
    async def languages() -> list[LanguageOut]:
        return [
            LanguageOut(
                code=code, name=lang.name, native=lang.native, tier=lang.tier, names=names_of(code)
            )
            for code, lang in LANGUAGES.items()
        ]

    @router.get("/quick-replies")
    async def quick_replies() -> QuickReplyTableOut:
        return QuickReplyTableOut(
            ids={role: list(ids) for role, ids in IDS_BY_ROLE.items()},
            languages={
                code: {
                    phrase_id: PhraseOut(text=phrase.text, review_status=phrase.review_status)
                    for phrase_id, phrase in phrases.items()
                }
                for code, phrases in QUICK_REPLIES.items()
            },
        )

    @router.get("/chrome")
    async def chrome() -> ChromeTableOut:
        return ChromeTableOut(
            languages={
                code: {
                    key: PhraseOut(text=phrase.text, review_status=phrase.review_status)
                    for key, phrase in strings.items()
                }
                for code, strings in CHROME.items()
            }
        )

    return router
