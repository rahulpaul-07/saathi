from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
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
    # Demo input lets a participant send a prepared clip instead of the microphone (off by default).
    demo_input: bool = Field(default=False, validation_alias="SAATHI_DEMO_INPUT")
    demo_clips_dir: Path = Field(
        default=Path("demo/clips"), validation_alias="SAATHI_DEMO_CLIPS_DIR"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # gnani_api_key is read from the environment
