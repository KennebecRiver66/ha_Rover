"""Polling coordinator for Rover Client."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
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
    CONF_SCAN_INTERVAL_HOURS,
    CONVERSATION_SCAN_DEPTH,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    ISSUE_SESSION_EXPIRED,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
    SESSION_BLOCKED,
    SESSION_SIGNED_IN,
)

LEARN_MORE_URL = (
    "https://github.com/KennebecRiver66/HARoverClient"
    "#when-the-session-expires"
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


def scan_interval(entry: RoverConfigEntry) -> timedelta:
    """Return the poll interval for an entry, clamped to something sane.

    Clamped here and not only in the options schema, because the stored value can
    also arrive from a hand-edited .storage file or an entry written by an older
    version, and a tight poll against a bot-protected endpoint is the one mistake
    this integration must not make on the user's behalf.
    """
    raw = entry.options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS)
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        _LOGGER.warning(
            "Ignoring unusable poll interval %r, falling back to %s hours",
            raw,
            DEFAULT_SCAN_INTERVAL_HOURS,
        )
        hours = float(DEFAULT_SCAN_INTERVAL_HOURS)

    clamped = min(max(hours, MIN_SCAN_INTERVAL_HOURS), MAX_SCAN_INTERVAL_HOURS)
    if clamped != hours:
        _LOGGER.warning(
            "Poll interval of %s hours is outside %s-%s hours, using %s",
            hours,
            MIN_SCAN_INTERVAL_HOURS,
            MAX_SCAN_INTERVAL_HOURS,
            clamped,
        )
    return timedelta(hours=clamped)


class RoverCoordinator(DataUpdateCoordinator[RoverData]):
    """Fetches conversations on a slow interval and shapes them for entities."""

    config_entry: RoverConfigEntry

    def __init__(self, hass: HomeAssistant, entry: RoverConfigEntry) -> None:
        """Set up the coordinator for one config entry."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval(entry),
            config_entry=entry,
        )
        self.client = RoverClient(
            async_get_clientsession(hass), entry.data[CONF_COOKIE]
        )
        self._issue_id = f"{ISSUE_SESSION_EXPIRED}_{entry.entry_id}"

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

        The auth path additionally raises a repair issue. ConfigEntryAuthFailed on
        its own only produces a reauth card inside Settings, which is easy to go
        weeks without noticing - and weeks of not noticing is exactly what happens
        to a cookie that expires every few weeks.
        """
        try:
            payload = await self.client.async_get_conversations()
        except RoverAuthError as err:
            self._async_create_session_issue()
            raise ConfigEntryAuthFailed(str(err)) from err
        except RoverBlockedError as err:
            # No issue raised and none cleared: a challenge says nothing either way
            # about whether the cookie is still good.
            _LOGGER.debug("Rover bot protection challenge: %s", err)
            return RoverData(session_state=SESSION_BLOCKED, detail=str(err))
        except RoverConnectionError as err:
            raise UpdateFailed(str(err)) from err

        self._async_clear_session_issue()
        return self._parse(payload)

    def _async_create_session_issue(self) -> None:
        """Surface a dead session on the Repairs dashboard."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            # Not fixable in place: the fix is pasting a fresh cookie, which the
            # reauth flow already does properly. A repair flow here would be a
            # second, divergent copy of that form.
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_SESSION_EXPIRED,
            translation_placeholders={"title": self.config_entry.title},
            learn_more_url=LEARN_MORE_URL,
        )

    def _async_clear_session_issue(self) -> None:
        """Drop the repair issue once a poll succeeds again."""
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)

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
