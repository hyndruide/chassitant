"""Conversation entity platform for Chassitant."""

from __future__ import annotations

import logging
from typing import Any, Literal

from homeassistant.components.conversation import (
    ConversationEntity,
    ConversationEntityFeature,
    ConversationInput,
    ConversationResult,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import ChassitantAuthError, ChassitantClient, ChassitantConnectionError
from .const import (
    CONF_EFFORT,
    CONF_MODEL,
    CONF_PROMPT,
    CONF_SKIP_PERMISSIONS,
    CONF_TIMEOUT,
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    DEFAULT_PROMPT,
    DEFAULT_SKIP_PERMISSIONS,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chassitant conversation entity from config entry."""
    client: ChassitantClient = hass.data[DOMAIN][entry.entry_id]["client"]
    async_add_entities([ChassitantConversationEntity(entry, client)])


class ChassitantConversationEntity(ConversationEntity):
    """Chassitant Assist conversation agent entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = ConversationEntityFeature.CONTROL

    def __init__(self, entry: ConfigEntry, client: ChassitantClient) -> None:
        """Initialize the conversation agent entity."""
        self.entry = entry
        self.client = client
        self._attr_unique_id = f"{entry.entry_id}_conversation"
        self._conversations_initialized: set[str] = set()

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages for conversation agent."""
        return "*"

    @property
    def device_info(self) -> DeviceInfo:
        """Return information about the device / service."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer="Google Antigravity",
            model="Antigravity CLI (agy)",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_process(self, user_input: ConversationInput) -> ConversationResult:
        """Process a conversational utterance through agy."""
        options = self.entry.options
        model = options.get(CONF_MODEL, DEFAULT_MODEL)
        effort = options.get(CONF_EFFORT, DEFAULT_EFFORT)
        system_prompt = options.get(CONF_PROMPT, DEFAULT_PROMPT)
        timeout = options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        skip_permissions = options.get(
            CONF_SKIP_PERMISSIONS, DEFAULT_SKIP_PERMISSIONS
        )

        conv_id = user_input.conversation_id
        text = user_input.text.strip()

        # Prepend system instructions on the first turn of a conversation thread
        is_first_turn = conv_id is None or conv_id not in self._conversations_initialized
        if is_first_turn and system_prompt:
            prompt_to_send = f"[Consignes système: {system_prompt}]\n\n{text}"
        else:
            prompt_to_send = text

        intent_response = intent.IntentResponse(language=user_input.language)

        try:
            result = await self.client.async_process(
                prompt=prompt_to_send,
                conversation_id=conv_id,
                model=model,
                effort=effort,
                dangerously_skip_permissions=skip_permissions,
                timeout=timeout,
            )

            if result.get("success"):
                response_text = result.get("response", "").strip()
                if not response_text:
                    response_text = "L'action a été exécutée avec succès."

                returned_conv_id = result.get("conversation_id") or conv_id
                if returned_conv_id:
                    self._conversations_initialized.add(returned_conv_id)

                intent_response.async_set_speech(response_text)
                return ConversationResult(
                    response=intent_response,
                    conversation_id=returned_conv_id,
                )

            # Failure reported by agy
            error_msg = result.get("error") or "Erreur inconnue retournée par l'agent."
            logger.error("Agy processing returned error: %s", error_msg)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Erreur Chassitant : {error_msg}",
            )
            return ConversationResult(
                response=intent_response,
                conversation_id=conv_id,
            )

        except ChassitantAuthError as err:
            logger.error("Authentication error: %s", err)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                "Erreur d'authentification avec la passerelle Chassitant.",
            )
            return ConversationResult(response=intent_response, conversation_id=conv_id)

        except ChassitantConnectionError as err:
            logger.error("Connection error: %s", err)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Impossible de joindre la passerelle Chassitant ({err}).",
            )
            return ConversationResult(response=intent_response, conversation_id=conv_id)

        except Exception as err:
            logger.exception("Unexpected error in Chassitant conversation: %s", err)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Une erreur imprévue est survenue : {err}",
            )
            return ConversationResult(response=intent_response, conversation_id=conv_id)
