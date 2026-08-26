"""Runtime settings, injected via environment / ``.env`` (never hardcoded).

The LLM layer (L4) is configured through these variables so the OpenAI-compatible
endpoint and model can be swapped without touching code:

* ``GUNGNIR_LLM_BASE_URL`` — OpenAI-compatible base URL (default: DeepSeek).
* ``GUNGNIR_LLM_API_KEY`` — API key. Empty means the LLM layer degrades to the
  deterministic template explanation (no network call).
* ``GUNGNIR_LLM_MODEL`` — model id (default: ``deepseek-chat``).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GUNGNIR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # TODO(待确认): the exact DeepSeek V4 model id on the platform's API. The
    # generic chat id below is a safe default; override with GUNGNIR_LLM_MODEL.
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"


settings = Settings()
