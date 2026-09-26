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
    BLOCKED_POLLS_BEFORE_REPAIR,
    CONF_COOKIE,
    CONF_SCAN_INTERVAL_HOURS,
    CONVERSATION_SCAN_DEPTH,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    ISSUE_BLOCKED,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
    SESSION_BLOCKED,
    SESSION_ERROR,
    SESSION_NOT_SIGNED_IN,
    SESSION_SIGNED_IN,
)

LEARN_MORE_URL = (
    "https://github.com/KennebecRiver66/HARoverClient#bot-challenges"
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
        self._issue_id = f"{ISSUE_BLOCKED}_{entry.entry_id}"
        # Counted in memory, so a restart forgives the streak. That is the right
        # way round: a repair that outlives the condition it describes is worse
        # than one raised a day late.
        self._blocked_polls = 0
        # Why the last poll failed, for the session sensor to report.
        #
        # Needed because a failure leaves `data` holding the last SUCCESSFUL poll,
        # so without this the diagnostic sensor would sit there saying "Signed in"
        # while nothing had got through for days - the precise failure this
        # integration is built to avoid, reproduced by the sensor meant to reveal it.
        self.failure_state: str | None = None

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

        The challenge path also counts. One challenge is routine, but a run of them
        means data has stopped arriving with nothing raised anywhere to say so -
        Home Assistant cannot know, because being blocked is reported as a state
        rather than a failure. After four in a row that becomes a repair.
        """
        try:
            payload = await self.client.async_get_conversations()
        except RoverAuthError as err:
            # No issue raised here: Home Assistant creates its own repair when this
            # exception starts a reauth flow, and that card opens the reauth dialog
            # directly. Adding a second one would just say the same thing twice.
            self.failure_state = SESSION_NOT_SIGNED_IN
            raise ConfigEntryAuthFailed(str(err)) from err
        except RoverBlockedError as err:
            _LOGGER.debug("Rover bot protection challenge: %s", err)
            self.failure_state = None
            self._blocked_polls += 1
            if self._blocked_polls >= BLOCKED_POLLS_BEFORE_REPAIR:
                self._async_create_blocked_issue()
            return RoverData(session_state=SESSION_BLOCKED, detail=str(err))
        except RoverConnectionError as err:
            self.failure_state = SESSION_ERROR
            self._blocked_polls = 0
            raise UpdateFailed(str(err)) from err

        self.failure_state = None
        self._blocked_polls = 0
        self._async_clear_blocked_issue()
        return self._parse(payload)

    def _async_create_blocked_issue(self) -> None:
        """Say out loud that Rover has been refusing us for a while."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            # Not fixable from here, because there is nothing to press: the fix is
            # waiting, and possibly lengthening the poll interval.
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_BLOCKED,
            translation_placeholders={
                "title": self.config_entry.title,
                "polls": str(self._blocked_polls),
            },
            learn_more_url=LEARN_MORE_URL,
        )

    def _async_clear_blocked_issue(self) -> None:
        """Drop the repair once a poll gets through again."""
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
