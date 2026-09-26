"""Config and reauth flow for Rover Client."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    RoverAuthError,
    RoverBlockedError,
    RoverClient,
    RoverConnectionError,
)
from .const import CONF_COOKIE, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_SCHEMA = vol.Schema({vol.Required(CONF_COOKIE): str})


class RoverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setting up and re-cookie-ing a Rover account.

    A reauth step exists from day one on purpose. The cookie this integration runs
    on is not permanent - a browser session cookie lasts weeks, not forever - so
    expiry is a NORMAL event, not an exceptional one. Without a reauth step the
    coordinator's ConfigEntryAuthFailed would have nowhere to land and the only
    recovery would be deleting and re-adding the integration.
    """

    VERSION = 1

    async def _async_validate(self, cookie: str) -> dict[str, str]:
        """Try the cookie for real and map the outcome to form errors.

        Validating by actually calling the API matters: a cookie can be
        well-formed and still be signed out, and finding that out at setup time is
        far kinder than a silently broken entry.
        """
        client = RoverClient(async_get_clientsession(self.hass), cookie)
        try:
            await client.async_get_conversations()
        except RoverAuthError:
            return {"base": "invalid_auth"}
        except RoverBlockedError:
            return {"base": "blocked"}
        except RoverConnectionError:
            return {"base": "cannot_connect"}
        # Ruff allows this blind except because the exception is logged below;
        # a config flow must never leak a traceback into the user's form.
        except Exception:
            _LOGGER.exception("Unexpected error validating the Rover cookie")
            return {"base": "unknown"}
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add the integration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            errors = await self._async_validate(cookie)
            if not errors:
                # One Rover account per Home Assistant. The cookie itself is not a
                # stable identity (it rotates), so the domain is the unique id.
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Rover", data={CONF_COOKIE: cookie}
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth after the coordinator reported the cookie is dead."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take a fresh cookie and write it over the existing entry.

        Updating the existing entry rather than creating a new one is what keeps
        entity IDs, history and any automations referencing them intact.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            errors = await self._async_validate(cookie)
            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_COOKIE: cookie}
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_SCHEMA, errors=errors
        )
