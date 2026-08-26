"""OllamaLLMProvider must read base_url/model from config.llm.options.ollama
(with defaults) and hand back a real agent_framework OllamaChatClient
configured with them - no live Ollama server required, construction alone
doesn't connect anywhere."""

from __future__ import annotations

from config.app_config import AppConfig, LLMConfig
from providers.ollama_llm_provider import OllamaLLMProvider


def test_defaults_when_no_options_given():
    provider = OllamaLLMProvider(AppConfig(llm=LLMConfig(provider="ollama")))
    assert provider.base_url == "http://localhost:11434"
    assert provider.model == "qwen3:14b"


def test_options_override_defaults():
    config = AppConfig(
        llm=LLMConfig(
            provider="ollama",
            options={"ollama": {"base_url": "http://ollama-host:9999", "model": "custom-model"}},
        )
    )
    provider = OllamaLLMProvider(config)
    assert provider.base_url == "http://ollama-host:9999"
    assert provider.model == "custom-model"


def test_get_chat_client_returns_configured_ollama_chat_client():
    from agent_framework.ollama import OllamaChatClient

    provider = OllamaLLMProvider(
        AppConfig(
            llm=LLMConfig(
                provider="ollama",
                options={"ollama": {"base_url": "http://localhost:11434", "model": "qwen3:14b"}},
            )
        )
    )
    client = provider.get_chat_client()

    assert isinstance(client, OllamaChatClient)


def test_get_chat_options_is_empty_when_no_options_given():
    provider = OllamaLLMProvider(AppConfig(llm=LLMConfig(provider="ollama")))
    assert provider.get_chat_options() == {}


def test_get_chat_options_passes_through_num_thread_temperature_seed():
    config = AppConfig(
        llm=LLMConfig(
            provider="ollama",
            options={"ollama": {"num_thread": 12, "temperature": 0.1, "seed": 42}},
        )
    )
    provider = OllamaLLMProvider(config)

    assert provider.get_chat_options() == {"num_thread": 12, "temperature": 0.1, "seed": 42}


def test_get_chat_options_allows_temperature_zero():
    config = AppConfig(
        llm=LLMConfig(provider="ollama", options={"ollama": {"temperature": 0}}),
    )
    provider = OllamaLLMProvider(config)

    assert provider.get_chat_options() == {"temperature": 0}
