"""Read-only public data the UI needs: the language table, the quick-reply table, feature flags."""

from collections.abc import Mapping

from fastapi import APIRouter
from pydantic import BaseModel

from saathi.languages import LANGUAGES, Tier
from saathi.quickreplies import IDS_BY_ROLE, QUICK_REPLIES, ReviewStatus
from saathi.rooms import Role


class LanguageOut(BaseModel):
    code: str
    name: str
    tier: Tier


class PhraseOut(BaseModel):
    text: str
    review_status: ReviewStatus


class QuickReplyTableOut(BaseModel):
    ids: dict[Role, list[str]]  # which phrase ids each role may send
    languages: dict[str, Mapping[str, PhraseOut]]  # language -> phrase id -> phrase


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
            LanguageOut(code=code, name=lang.name, tier=lang.tier)
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

    return router
