"""Provider Factory and Registry for Françoise."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from bridge.providers.base import BaseProvider
from bridge.providers.agy_provider import AgyProvider
from bridge.providers.codex_provider import CodexProvider
from bridge.providers.openai_compatible_provider import OpenAICompatibleProvider

logger = logging.getLogger("chassitant.providers.factory")


class ProviderFactory:
    """Manages available providers and instantiates the active one."""

    def __init__(self, auth_manager: Any, agy_client: Any) -> None:
        self.auth_manager = auth_manager
        self.agy_client = agy_client
        self._providers: Dict[str, BaseProvider] = {}
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        cfg = self.auth_manager._config

        # 1. Google Antigravity (agy)
        self._providers["agy"] = AgyProvider(self.agy_client)

        # 2. Groq (Free fast models)
        groq_key = os.getenv("GROQ_API_KEY") or cfg.get("groq_api_key", "")
        self._providers["groq"] = OpenAICompatibleProvider(
            provider_id="groq",
            display_name="Groq (Llama 3.3 70B Gratuit)",
            description="Llama 3.3 70B gratuit et ultra-rapide (~500 tokens/s, 30 req/min).",
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key,
            default_model=cfg.get("groq_model", "llama-3.3-70b-versatile"),
        )

        # 3. OpenRouter (Free :free & paid models)
        openrouter_key = os.getenv("OPENROUTER_API_KEY") or cfg.get("openrouter_api_key", "")
        self._providers["openrouter"] = OpenAICompatibleProvider(
            provider_id="openrouter",
            display_name="OpenRouter (DeepSeek R1 :free & autres)",
            description="Modèles gratuits (DeepSeek R1, Llama 3.3 :free) ou premium via une clé OpenRouter.",
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_key,
            default_model=cfg.get("openrouter_model", "deepseek/deepseek-r1:free"),
        )

        # 4. Ollama (Local models)
        ollama_url = os.getenv("OLLAMA_URL") or cfg.get("ollama_url", "http://localhost:11434/v1")
        self._providers["ollama"] = OpenAICompatibleProvider(
            provider_id="ollama",
            display_name="Ollama (Modèles Locaux)",
            description="100% gratuit, privé et local sur votre réseau domestique (ex: Llama 3.2, Qwen 2.5).",
            base_url=ollama_url,
            api_key="ollama",
            default_model=cfg.get("ollama_model", "llama3.2"),
        )

        # 5. OpenAI Codex CLI (ChatGPT Account or API Key)
        codex_key = os.getenv("OPENAI_API_KEY") or cfg.get("codex_api_key", "")
        self._providers["codex"] = CodexProvider(api_key=codex_key)

    def get_active_provider_id(self) -> str:
        # Default to 'agy' if not set
        return self.auth_manager._config.get("active_provider", "agy")

    def get_active_provider(self) -> BaseProvider:
        pid = self.get_active_provider_id()
        if pid not in self._providers:
            pid = "agy"
        return self._providers[pid]

    def set_active_provider(self, provider_id: str) -> bool:
        if provider_id not in self._providers:
            return False
        self.auth_manager._config["active_provider"] = provider_id
        self.auth_manager.save_config()
        logger.info("Switched active AI provider to '%s'", provider_id)
        return True

    def update_provider_config(self, provider_id: str, new_config: Dict[str, Any]) -> None:
        cfg = self.auth_manager._config
        if provider_id == "groq":
            if "api_key" in new_config:
                cfg["groq_api_key"] = new_config["api_key"].strip()
            if "model" in new_config:
                cfg["groq_model"] = new_config["model"].strip()
        elif provider_id == "openrouter":
            if "api_key" in new_config:
                cfg["openrouter_api_key"] = new_config["api_key"].strip()
            if "model" in new_config:
                cfg["openrouter_model"] = new_config["model"].strip()
        elif provider_id == "ollama":
            if "url" in new_config:
                cfg["ollama_url"] = new_config["url"].strip()
            if "model" in new_config:
                cfg["ollama_model"] = new_config["model"].strip()
        elif provider_id == "codex":
            if "api_key" in new_config:
                cfg["codex_api_key"] = new_config["api_key"].strip()
            if "model" in new_config:
                cfg["codex_model"] = new_config["model"].strip()

        self.auth_manager.save_config()
        # Re-initialize providers with updated settings
        self._initialize_providers()

    def list_providers(self) -> List[Dict[str, Any]]:
        active_id = self.get_active_provider_id()
        result = []
        for pid, prov in self._providers.items():
            result.append({
                "id": pid,
                "name": prov.display_name,
                "description": prov.description,
                "is_active": (pid == active_id),
                "is_configured": prov.is_configured(),
                "models": prov.list_models(),
                "quota": prov.get_quota_status(),
                "config": {
                    "api_key_set": bool(getattr(prov, "api_key", False)),
                    "base_url": getattr(prov, "base_url", ""),
                    "default_model": getattr(prov, "default_model", ""),
                },
            })
        return result

    def get_all_quotas(self) -> Dict[str, Any]:
        """Return quota and allowance status for all providers."""
        return {pid: prov.get_quota_status() for pid, prov in self._providers.items()}
