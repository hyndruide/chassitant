"""Google Antigravity CLI (agy) Provider implementation."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from bridge.providers.base import BaseProvider

logger = logging.getLogger("chassitant.providers.agy")


class AgyProvider(BaseProvider):
    """Provider integrating Google Antigravity CLI (agy)."""

    def __init__(self, agy_client: Any) -> None:
        self.client = agy_client

    @property
    def provider_id(self) -> str:
        return "agy"

    @property
    def display_name(self) -> str:
        return "Google Antigravity (agy)"

    @property
    def description(self) -> str:
        return "Compte Google OAuth avec quota gratuit Gemini inclus (15 req/min, 0 € par token)."

    def is_configured(self) -> bool:
        return self.client.is_installed()

    def check_auth(self, timeout: int = 15) -> Tuple[bool, str]:
        return self.client.check_auth(timeout=timeout)

    def list_models(self) -> List[Dict[str, str]]:
        models = self.client.list_models()
        if not models:
            # Fallback default Gemini models available on Google Antigravity
            return [
                {"id": "default", "name": "Gemini (Par défaut / Flash)"},
                {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash (Rapide)"},
                {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro (Raisonnement)"},
                {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash-Lite"},
            ]
        return models

    def get_quota_status(self) -> Dict[str, Any]:
        """Fetch quota and account tier status for Google Antigravity / Gemini."""
        import json
        from pathlib import Path

        oauth_file = Path.home() / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
        account_email = None
        auth_method = "consumer"

        if oauth_file.is_file():
            try:
                with open(oauth_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    account_email = data.get("id_token_email")
                    auth_method = data.get("auth_method") or "consumer"
            except Exception:
                pass

        is_auth, _ = self.check_auth(timeout=5)
        if not is_auth:
            return {
                "provider": "agy",
                "display_name": self.display_name,
                "plan": "Non connecté",
                "is_authenticated": False,
                "summary": "Non connecté à Google (ouvrir Connexion)",
            }

        plan_desc = "Google One AI Premium / Gemini Advanced" if auth_method == "consumer" else f"Google Cloud ({auth_method})"
        summary = f"{account_email} • Quota Gemini inclus (0 € / token)" if account_email else "Compte Google connecté • Forfait Gemini inclus"

        return {
            "provider": "agy",
            "display_name": self.display_name,
            "plan": plan_desc,
            "account": account_email,
            "is_authenticated": True,
            "quota_type": "subscription_included",
            "summary": summary,
            "note": "Google applique un quota d'utilisation équitable (fair-use) sans facturation au token.",
        }

    def process_stream(
        self,
        prompt: str,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        timeout: int = 300,
        pre_prompt: Optional[str] = None,
        on_proc_started: Optional[Callable[[Any], None]] = None,
        cancel_event: Optional[Any] = None,
    ) -> Iterator[Dict[str, Any]]:
        # Inject pre-prompt if provided
        effective_prompt = prompt
        if pre_prompt and pre_prompt.strip():
            effective_prompt = f"[Consignes système / Pré-prompt : {pre_prompt.strip()}]\n\n{prompt}"

        return self.client.process_stream(
            prompt=effective_prompt,
            conversation_id=conversation_id,
            model=model,
            effort=effort,
            dangerously_skip_permissions=True,
            timeout=timeout,
            on_proc_started=on_proc_started,
            cancel_event=cancel_event,
        )
