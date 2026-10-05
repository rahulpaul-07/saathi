from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gnani_api_key: SecretStr
    gnani_base_url: str = "https://api.vachana.ai"
    gnani_timeout_s: float = 30.0
    # 1 = greedy. Slice 5 compares it against beam search on FLORES before it is trusted.
    translator_num_beams: int = Field(default=1, ge=1, le=10)
    # Each turn spends Gnani credits, so the public endpoint is capped per client IP.
    turn_rate_limit_per_minute: int = Field(default=10, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # gnani_api_key is read from the environment
