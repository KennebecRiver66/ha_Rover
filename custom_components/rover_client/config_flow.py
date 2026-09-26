"""Config, reauth and options flows for Rover Client."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    RoverAuthError,
    RoverBlockedError,
    RoverClient,
    RoverConnectionError,
)
from .const import (
    CONF_COOKIE,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
)
from .cookie import cookie_problem, normalise_cookie
from .coordinator import RoverConfigEntry

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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: RoverConfigEntry) -> RoverOptionsFlow:
        """Return the options flow for changing the poll interval."""
        return RoverOptionsFlow()

    async def _async_validate(self, cookie: str) -> dict[str, str]:
        """Try the cookie for real and map the outcome to form errors.

        Shape is checked locally first so that the two mistakes that look alike
        stay distinguishable: a single pasted cookie is caught here as
        `partial_cookie`, while a whole header from a signed-out browser can only
        be caught by Rover and comes back as `invalid_auth`. Reporting both as
        "Rover rejected that cookie" is what makes setup feel like guesswork.

        Validating the rest by actually calling the API matters too: a cookie can
        be well-formed and still be signed out, and finding that out at setup time
        is far kinder than a silently broken entry.
        """
        if problem := cookie_problem(cookie):
            return {"base": problem}

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
            cookie = normalise_cookie(user_input[CONF_COOKIE])
            errors = await self._async_validate(cookie)
            if not errors:
                # One Rover account per Home Assistant. The cookie itself is not a
                # stable identity (it rotates), so the domain is the unique id.
                # This limitation is documented in the README; lifting it needs an
                # account identifier, and the one endpoint reachable with a cookie
                # does not carry one.
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
            cookie = normalise_cookie(user_input[CONF_COOKIE])
            errors = await self._async_validate(cookie)
            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_COOKIE: cookie}
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_SCHEMA, errors=errors
        )


class RoverOptionsFlow(OptionsFlow):
    """Let the poll interval be lengthened - and only barely shortened.

    The floor is one hour and is enforced in three places: the selector, the
    schema, and again when the coordinator reads the value. That is not paranoia
    about the user, it is that the cost of getting this wrong is Rover's bot
    detection flagging the household's IP, which is not a failure the user can
    debug. The UI says as much rather than leaving the floor unexplained.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and save the poll interval."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_HOURS, default=current
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_HOURS,
                        max=MAX_SCAN_INTERVAL_HOURS,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="hours",
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
