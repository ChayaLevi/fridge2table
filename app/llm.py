"""Model factories. Every model is built from an env string (see `app/config.py`).

The DeepSeek API is OpenAI-compatible. We use Pydantic AI's `DeepSeekProvider` (it knows
DeepSeek's thinking/tool-choice quirks) but hand it our own client, so `DEEPSEEK_BASE_URL`
stays configurable. Another OpenAI-compatible vendor (e.g. Qwen) can be added with
`build_model(..., provider="openai-compatible", base_url=..., api_key=...)`.
"""

import logging
import os

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from app import config

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

log = logging.getLogger(__name__)

# Current DeepSeek IDs that pydantic-ai 2.55 does not know yet, mapped to the known ID whose
# profile fits. `deepseek-flash` (V4.1-Flash) thinks by default like `deepseek-v4-flash`; without
# this, pydantic-ai forces `tool_choice` and DeepSeek answers 400 "Thinking mode does not
# support this tool_choice".
_DEEPSEEK_PROFILE_ALIASES = {"deepseek-flash": "deepseek-v4-flash"}


def build_model(
    model_id: str,
    *,
    provider: str = "deepseek",
    base_url: str | None = None,
    api_key: str | None = None,
) -> OpenAIChatModel:
    if provider == "deepseek":
        api_key = api_key or config.DEEPSEEK_API_KEY
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set (see .env.example)")
        client = AsyncOpenAI(base_url=base_url or config.DEEPSEEK_BASE_URL, api_key=api_key)
        profile = DeepSeekProvider.model_profile(_DEEPSEEK_PROFILE_ALIASES.get(model_id, model_id))
        return OpenAIChatModel(model_id, provider=DeepSeekProvider(openai_client=client), profile=profile)
    if provider == "openai-compatible":
        if not (base_url and api_key):
            raise RuntimeError(f"provider {provider!r} needs base_url and api_key")
        return OpenAIChatModel(model_id, provider=OpenAIProvider(base_url=base_url, api_key=api_key))
    raise ValueError(f"unknown provider {provider!r}")


def thinking_settings(enabled: bool) -> ModelSettings:
    """Model settings that turn DeepSeek's thinking mode on or off (pydantic-ai's unified `thinking` key).

    DeepSeek V4 models think by default (`thinking_enabled_by_default` in the provider profile); `False`
    is sent as `reasoning_effort: none`, which the API accepts (checked 2026-10-13). FunctionModels in
    tests ignore the setting.
    """
    return ModelSettings(thinking=enabled)


def vision_model() -> OpenAIChatModel:
    return build_model(config.VISION_MODEL)


def agent_model() -> OpenAIChatModel:
    return build_model(config.AGENT_MODEL)


def recipe_model() -> OpenAIChatModel:
    return build_model(config.RECIPE_MODEL)


def setup_observability() -> None:
    """`LOG_LEVEL` for plain logging; Logfire instrumentation only if `LOGFIRE_TOKEN` is set."""
    logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if config.LOG_LEVEL.upper() != "DEBUG":  # one line per HTTP request is noise below DEBUG
        for name in ("httpx", "httpx2", "openai"):
            logging.getLogger(name).setLevel(logging.WARNING)
    if not config.LOGFIRE_TOKEN:
        return
    try:
        import logfire
    except ImportError:
        log.warning("LOGFIRE_TOKEN is set but the `logfire` package is not installed; skipping")
        return
    logfire.configure(token=config.LOGFIRE_TOKEN, send_to_logfire="if-token-present")
    logfire.instrument_pydantic_ai()
