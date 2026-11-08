"""Services for the Chassitant integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers import config_validation as cv

from .client import ChassitantClient
from .const import DOMAIN, SERVICE_ASK, SERVICE_CLEAR_CONVERSATION

logger = logging.getLogger(__name__)

ASK_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("prompt"): cv.string,
        vol.Optional("conversation_id"): cv.string,
        vol.Optional("model"): cv.string,
        vol.Optional("effort"): cv.string,
    }
)

CLEAR_CONV_SCHEMA = vol.Schema(
    {
        vol.Optional("conversation_id"): cv.string,
    }
)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register Chassitant services."""

    def _get_default_client() -> ChassitantClient:
        entries = hass.data.get(DOMAIN, {})
        for entry_id, data in entries.items():
            if "client" in data:
                return data["client"]
        raise ValueError("Aucune instance Chassitant configurée active.")

    async def async_handle_ask(call: ServiceCall) -> ServiceResponse:
        """Handle the chassitant.ask service call."""
        client = _get_default_client()
        prompt = call.data["prompt"]
        conversation_id = call.data.get("conversation_id")
        model = call.data.get("model")
        effort = call.data.get("effort")

        result = await client.async_process(
            prompt=prompt,
            conversation_id=conversation_id,
            model=model,
            effort=effort,
        )

        return {
            "success": result.get("success", False),
            "response": result.get("response", ""),
            "conversation_id": result.get("conversation_id", ""),
            "duration_seconds": result.get("duration_seconds", 0),
            "usage": result.get("usage", {}),
        }

    async def async_handle_clear_conv(call: ServiceCall) -> None:
        """Handle clearing a conversation session."""
        conv_id = call.data.get("conversation_id")
        logger.info("Clearing conversation thread: %s", conv_id or "all")

    if not hass.services.has_service(DOMAIN, SERVICE_ASK):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ASK,
            async_handle_ask,
            schema=ASK_SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_CONVERSATION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_CONVERSATION,
            async_handle_clear_conv,
            schema=CLEAR_CONV_SCHEMA,
        )
