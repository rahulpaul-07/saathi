import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    gnani_api_key: SecretStr
    gnani_base_url: str = "https://api.vachana.ai"
    gnani_timeout_s: float = 30.0
    # 1 = greedy. Slice 5 compares it against beam search on FLORES before it is trusted.
    translator_num_beams: int = Field(default=1, ge=1, le=10)
    # Each turn spends Gnani credits, so the public endpoint is capped per client IP.
    turn_rate_limit_per_minute: int = Field(default=10, ge=1)
    # Room codes carry about 30 bits, so create and join attempts are capped per client IP.
    room_rate_limit_per_minute: int = Field(default=10, ge=1)
    # Quick replies and chip replies push an event to the other screen (and a quick reply may spend
    # a TTS call), so each participant is capped, not each IP: two phones can share one.
    reply_rate_limit_per_minute: int = Field(default=30, ge=1)
    max_rooms: int = Field(default=50, ge=1)
    # One short TTS call at startup, because the first TTS after idle took 15.9 s live against
    # 1.2-5.3 s afterwards. It spends a Gnani call each start, so it is off by default.
    warm_tts: bool = Field(default=False, validation_alias="SAATHI_WARM_TTS")
    # Demo input lets a participant send a prepared clip instead of the microphone (off by default).
    demo_input: bool = Field(default=False, validation_alias="SAATHI_DEMO_INPUT")
    # "conditional" restores floor, cross and main as ordinals where the target lexicon has the word
    # (docs/EVAL.md). It is an experiment: "current" stays the default until it is measured better.
    masking_mode: Literal["current", "conditional"] = Field(
        default="current", validation_alias="SAATHI_MASKING_MODE"
    )
    demo_clips_dir: Path = Field(
        default=Path("demo/clips"), validation_alias="SAATHI_DEMO_CLIPS_DIR"
    )

    # Public hosting. Everything below is ignored unless SAATHI_PUBLIC is set.
    # Not named `public`: Windows defines a PUBLIC variable that would be parsed as this field.
    public_mode: bool = Field(default=False, validation_alias="SAATHI_PUBLIC")
    # Comma-separated IPs or CIDRs of the reverse proxies whose X-Forwarded-For may be believed.
    trusted_proxies: str = Field(default="", validation_alias="SAATHI_TRUSTED_PROXIES")
    # Gnani HTTP attempts allowed per UTC day, retries included. 0 disables live calls.
    daily_gnani_budget: int = Field(default=200, ge=0, validation_alias="SAATHI_DAILY_GNANI_BUDGET")
    budget_file: Path = Field(
        default=Path("data/gnani_budget.json"), validation_alias="SAATHI_BUDGET_FILE"
    )
    # Env switch (needs a restart) and kill file (checked on every call, no restart needed).
    kill_switch: bool = Field(default=False, validation_alias="SAATHI_KILL_SWITCH")
    kill_file: Path | None = Field(default=None, validation_alias="SAATHI_KILL_FILE")
    public_max_rooms: int = Field(default=20, ge=1, validation_alias="SAATHI_PUBLIC_MAX_ROOMS")
    room_idle_ttl_s: float = Field(default=600.0, gt=0, validation_alias="SAATHI_ROOM_IDLE_TTL_S")
    room_hard_ttl_s: float = Field(default=3600.0, gt=0, validation_alias="SAATHI_ROOM_HARD_TTL_S")
    room_creates_per_hour: int = Field(
        default=6, ge=1, validation_alias="SAATHI_ROOM_CREATES_PER_HOUR"
    )
    max_upload_bytes: int = Field(
        default=1_000_000, ge=1000, le=2_500_000, validation_alias="SAATHI_MAX_UPLOAD_BYTES"
    )
    # Public origin used in the QR code (https://host, no path). Unset: the request's own origin,
    # which is wrong behind a TLS-terminating proxy because the app sees plain http there.
    public_base_url: str | None = Field(default=None, validation_alias="SAATHI_PUBLIC_BASE_URL")
    demo_bundle_dir: Path = Field(
        default=Path("demo/bundle"), validation_alias="SAATHI_DEMO_BUNDLE_DIR"
    )

    @field_validator("kill_file", "public_base_url", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        # An empty kill-file variable would otherwise become Path("."), which exists, and stop
        # every call.
        return None if value == "" else value

    @field_validator("public_base_url")
    @classmethod
    def _base_url_is_an_origin(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?", value):
            raise ValueError("SAATHI_PUBLIC_BASE_URL must look like https://host[:port], no path")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # gnani_api_key is read from the environment
