import pytest
from pydantic_ai.models.openai import OpenAIChatModel

from app import config
from app.llm import build_model


def test_deepseek_model_from_id():
    m = build_model("deepseek-v4-pro", api_key="k")
    assert isinstance(m, OpenAIChatModel)
    assert m.model_name == "deepseek-v4-pro" and m.system == "deepseek"
    assert str(m.client.base_url).rstrip("/") == config.DEEPSEEK_BASE_URL.rstrip("/")


def test_base_url_is_configurable():
    m = build_model("deepseek-v4-pro", api_key="k", base_url="https://example.test/v1")
    assert str(m.client.base_url).rstrip("/") == "https://example.test/v1"


def test_deepseek_flash_gets_thinking_profile():
    # Without this, pydantic-ai forces tool_choice and DeepSeek rejects it (HTTP 400).
    profile = build_model("deepseek-flash", api_key="k").profile
    assert profile["thinking_enabled_by_default"] is True
    assert profile["supports_forced_tool_choice_with_thinking"] is False


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", None)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        build_model("deepseek-v4-pro")


def test_openai_compatible_provider():
    m = build_model("qwen3.8-max", provider="openai-compatible", base_url="https://example.test/v1", api_key="k")
    assert m.model_name == "qwen3.8-max"
    with pytest.raises(RuntimeError):
        build_model("qwen3.8-max", provider="openai-compatible")
    with pytest.raises(ValueError):
        build_model("x", provider="nope")
