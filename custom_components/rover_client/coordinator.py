"""Polling coordinator for Rover Client."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    RoverAuthError,
    RoverBlockedError,
    RoverClient,
    RoverConnectionError,
)
from .const import (
    CONF_COOKIE,
    CONVERSATION_SCAN_DEPTH,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SESSION_BLOCKED,
    SESSION_SIGNED_IN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RoverData:
    """Everything the entities need from one poll.

    A dataclass rather than a raw dict so that adding a field is a typed change
    and a typo in an entity becomes an AttributeError instead of a silent None.
    """

    session_state: str = SESSION_SIGNED_IN
    conversation_count: int = 0
    latest_service_type: str | None = None
    latest_sitter: str | None = None
    # sitter first name -> service type, newest booking wins.
    service_types: dict[str, str] = field(default_factory=dict)
    detail: str | None = None


type RoverConfigEntry = ConfigEntry[RoverCoordinator]


class RoverCoordinator(DataUpdateCoordinator[RoverData]):
    """Fetches conversations on a slow interval and shapes them for entities."""

    config_entry: RoverConfigEntry

    def __init__(self, hass: HomeAssistant, entry: RoverConfigEntry) -> None:
        """Set up the coordinator for one config entry."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = RoverClient(
            async_get_clientsession(hass), entry.data[CONF_COOKIE]
        )

    async def _async_update_data(self) -> RoverData:
        """Poll once and translate failures into the right HA reaction.

        The translation is the whole point of this method:

        - RoverAuthError -> ConfigEntryAuthFailed, which starts the reauth flow so
          the user is ASKED for a fresh cookie. Logging and carrying on would leave
          entities frozen at their last value with nothing to explain why, which is
          the failure mode this integration exists to avoid.
        - RoverBlockedError -> a reported state, not an exception. The cookie is
          probably fine; a challenge is temporary and the next poll is six hours
          away anyway. Raising UpdateFailed here would mark entities unavailable
          and lose the one piece of information worth having: that we were blocked.
        - RoverConnectionError -> UpdateFailed, the ordinary transient path.
        """
        try:
            payload = await self.client.async_get_conversations()
        except RoverAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RoverBlockedError as err:
            _LOGGER.debug("Rover bot protection challenge: %s", err)
            return RoverData(session_state=SESSION_BLOCKED, detail=str(err))
        except RoverConnectionError as err:
            raise UpdateFailed(str(err)) from err

        return self._parse(payload)

    @staticmethod
    def _parse(payload: dict[str, Any]) -> RoverData:
        """Shape the raw payload into RoverData.

        Defensive throughout: this is an undocumented API that can change without
        warning, so a missing or reshaped field must degrade to None rather than
        raise and take the whole integration offline.
        """
        results = payload.get("results") or []
        if not isinstance(results, list):
            results = []

        data = RoverData(
            session_state=SESSION_SIGNED_IN,
            conversation_count=len(results),
        )

        for conversation in results[:CONVERSATION_SCAN_DEPTH]:
            if not isinstance(conversation, dict):
                continue

            service_type = conversation.get("service_type")
            provider = conversation.get("provider")
            sitter = (
                provider.get("first_name") if isinstance(provider, dict) else None
            )

            if data.latest_service_type is None and service_type:
                data.latest_service_type = str(service_type)
                data.latest_sitter = str(sitter) if sitter else None

            # First occurrence wins because results arrive newest first. This is
            # what lets several bookings made in one sitting each keep their own
            # service type, instead of every consumer reading whichever booking
            # happens to be newest overall.
            if sitter and service_type and sitter not in data.service_types:
                data.service_types[str(sitter)] = str(service_type)

        return data
