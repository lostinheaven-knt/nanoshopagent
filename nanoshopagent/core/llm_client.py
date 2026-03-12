from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI


@dataclass(frozen=True)
class LLMConfig:
    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url_env: str = "DEEPSEEK_BASE_URL"
    model_env: str = "DEEPSEEK_MODEL"

    model: str = "deepseek-chat"
    temperature: float = 0.0


def make_client(cfg: LLMConfig) -> OpenAI:
    api_key = os.environ.get(cfg.api_key_env)
    base_url = os.environ.get(cfg.base_url_env)

    if not api_key:
        raise RuntimeError(
            f"Missing {cfg.api_key_env}. Load .secrets.env or set env vars."
        )
    if not base_url:
        raise RuntimeError(
            f"Missing {cfg.base_url_env}. Load .secrets.env or set env vars."
        )

    return OpenAI(api_key=api_key, base_url=base_url)


def resolve_model(cfg: LLMConfig) -> str:
    return os.environ.get(cfg.model_env) or cfg.model
