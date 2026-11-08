"""API Client for Chassitant Bridge in Home Assistant."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

logger = logging.getLogger(__name__)


class ChassitantClientError(Exception):
    """Base exception for Chassitant API errors."""


class ChassitantAuthError(ChassitantClientError):
    """Authentication failed exception."""


class ChassitantConnectionError(ChassitantClientError):
    """Connection failure exception."""


class ChassitantClient:
    """Handles communication with the Chassitant Bridge server."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        api_key: str,
        timeout: int = 60,
    ) -> None:
        self.hass = hass
        self.host = host
        self.port = port
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"

    @property
    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"
        return headers

    async def async_test_connection(self) -> tuple[bool, str, dict[str, Any]]:
        """
        Verify connection and authentication with the bridge.
        Returns (success, message, data).
        """
        session = async_get_clientsession(self.hass)

        # Candidates to try if connecting from inside Home Assistant OS
        candidate_hosts = [self.host]
        if self.host in ("localhost", "127.0.0.1", "c211720a-chassitant-agy"):
            for h in ("c211720a-chassitant-agy", "localhost", "127.0.0.1"):
                if h not in candidate_hosts:
                    candidate_hosts.append(h)

        last_error = ""
        for host in candidate_hosts:
            url = f"http://{host}:{self.port}/api/auth/check"
            try:
                async with session.post(
                    url,
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 401:
                        return False, "Jeton API invalide (Unauthorized)", {}

                    if response.status == 200:
                        data = await response.json()
                        # Update working host and base_url
                        self.host = host
                        self.base_url = f"http://{host}:{self.port}"
                        return True, "Connexion réussie !", data
            except Exception as err:
                last_error = str(err)
                continue

        return False, f"Impossible de joindre l'Add-on Chassitant: {last_error}", {}

    async def async_process(
        self,
        prompt: str,
        conversation_id: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        dangerously_skip_permissions: bool = True,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Send prompt to agy via the bridge server."""
        session = async_get_clientsession(self.hass)
        url = f"{self.base_url}/api/process"

        eff_timeout = timeout or self.timeout
        payload = {
            "prompt": prompt,
            "conversation_id": conversation_id,
            "model": model,
            "effort": effort,
            "dangerously_skip_permissions": dangerously_skip_permissions,
            "timeout": eff_timeout,
        }

        # Extra 15s network margin
        client_timeout = aiohttp.ClientTimeout(total=eff_timeout + 15)

        try:
            async with session.post(
                url,
                headers=self._headers,
                json=payload,
                timeout=client_timeout,
            ) as response:
                if response.status == 401:
                    raise ChassitantAuthError("Jeton d'authentification invalide.")

                data = await response.json()
                return data

        except aiohttp.ClientConnectorError as err:
            raise ChassitantConnectionError(
                f"Impossible de contacter le Bridge Chassitant: {err}"
            ) from err
        except asyncio.TimeoutError as err:
            raise ChassitantConnectionError(
                f"Délai d'attente dépassé ({eff_timeout}s) pour la réponse d'agy."
            ) from err

    async def async_get_models(self) -> list[dict[str, str]]:
        """Fetch list of supported models from the bridge."""
        session = async_get_clientsession(self.hass)
        url = f"{self.base_url}/api/models"

        try:
            async with session.get(
                url,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("models", [])
        except Exception as err:
            logger.warning("Failed to retrieve models from bridge: %s", err)

        return []
