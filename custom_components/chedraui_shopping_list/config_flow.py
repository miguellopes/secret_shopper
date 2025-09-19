"""Config flow for the Chedraui Shopping List integration."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .api import ChedrauiAuthError, ChedrauiClient, ChedrauiRequestError
from .const import CONF_STORE_ID, DEFAULT_STORE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ChedrauiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the integration."""

    VERSION = 1

    def __init__(self) -> None:
        self._errors: dict[str, str] = {}

    async def async_step_user(
        self, user_input: Mapping[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is None:
            return self._show_form()

        username = str(user_input[CONF_USERNAME]).strip()
        password = str(user_input[CONF_PASSWORD])
        store_id = str(user_input.get(CONF_STORE_ID, DEFAULT_STORE_ID))

        try:
            await self._async_validate(username, password, store_id)
        except ChedrauiAuthError:
            self._errors["base"] = "auth"
            return self._show_form(user_input)
        except ChedrauiRequestError:
            self._errors["base"] = "cannot_connect"
            return self._show_form(user_input)

        await self.async_set_unique_id(username.lower())
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Chedraui ({username})",
            data={
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
                CONF_STORE_ID: store_id,
            },
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> config_entries.FlowResult:
        self.context["entry_id"] = entry_data["entry_id"]
        return await self.async_step_user()

    async def async_step_reauth_confirm(
        self, user_input: Mapping[str, Any] | None = None
    ) -> config_entries.FlowResult:
        entry_id = self.context.get("entry_id")
        if entry_id is None:
            return self.async_abort(reason="unknown")
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return self.async_abort(reason="unknown")
        if user_input is None:
            user_input = {
                CONF_USERNAME: entry.data[CONF_USERNAME],
                CONF_PASSWORD: entry.data[CONF_PASSWORD],
                CONF_STORE_ID: entry.data.get(CONF_STORE_ID, DEFAULT_STORE_ID),
            }
        return await self.async_step_user(user_input)

    async def _async_validate(self, username: str, password: str, store_id: str) -> None:
        session = self.hass.helpers.aiohttp_client.async_get_clientsession()
        client = ChedrauiClient(
            session=session,
            username=username,
            password=password,
            store_id=store_id,
        )
        await client.async_login()

    def _show_form(
        self, user_input: Mapping[str, Any] | None = None
    ) -> config_entries.FlowResult:
        user_input = dict(user_input or {})
        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "")): str,
                vol.Optional(
                    CONF_STORE_ID,
                    default=user_input.get(CONF_STORE_ID, DEFAULT_STORE_ID),
                ): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=self._errors
        )
