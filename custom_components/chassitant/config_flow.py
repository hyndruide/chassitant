"""Config flow and Options flow for Chassitant integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .client import ChassitantClient
from .const import (
    CONF_API_KEY,
    CONF_EFFORT,
    CONF_HOST,
    CONF_MODEL,
    CONF_PORT,
    CONF_PROMPT,
    CONF_SKIP_PERMISSIONS,
    CONF_TIMEOUT,
    DEFAULT_EFFORT,
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_PROMPT,
    DEFAULT_SKIP_PERMISSIONS,
    DEFAULT_TIMEOUT,
    DOMAIN,
    EFFORT_OPTIONS,
)

logger = logging.getLogger(__name__)


class ChassitantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Chassitant."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            api_key = user_input.get(CONF_API_KEY, "").strip()

            client = ChassitantClient(
                hass=self.hass,
                host=host,
                port=port,
                api_key=api_key,
                timeout=15,
            )

            success, msg, _ = await client.async_test_connection()

            if not success:
                logger.warning("Connection test failed: %s", msg)
                if "Unauthorized" in msg or "Jeton API invalide" in msg:
                    errors["base"] = "invalid_auth"
                elif "Le CLI agy n'est pas encore connecté" in msg:
                    errors["base"] = "agy_not_authenticated"
                else:
                    errors["base"] = "cannot_connect"
            else:
                host = client.host
                user_input[CONF_HOST] = host
                unique_id = f"chassitant_{host}_{port}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                title = f"Antigravity agy ({host}:{port})"
                return self.async_create_entry(title=title, data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_API_KEY, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return ChassitantOptionsFlowHandler(config_entry)


class ChassitantOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Chassitant."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Retrieve current options or fallback to entry data or defaults
        options = self.config_entry.options
        current_model = options.get(CONF_MODEL, DEFAULT_MODEL)
        current_effort = options.get(CONF_EFFORT, DEFAULT_EFFORT)
        current_prompt = options.get(CONF_PROMPT, DEFAULT_PROMPT)
        current_timeout = options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        current_skip_perm = options.get(
            CONF_SKIP_PERMISSIONS, DEFAULT_SKIP_PERMISSIONS
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_MODEL, default=current_model): str,
                vol.Optional(CONF_EFFORT, default=current_effort): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=EFFORT_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_PROMPT, default=current_prompt): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(CONF_TIMEOUT, default=current_timeout): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=300,
                        step=5,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_SKIP_PERMISSIONS, default=current_skip_perm
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
