"""Services for Rover Client.

One service, and it sends nothing. It composes a reminder and hands it back, for
two reasons that are worth stating because "why doesn't it just message the
sitter" is the obvious first question:

- Rover cannot be written to from here. This integration reads one endpoint that
  happens not to sit behind Rover's bot challenge; posting a message is a
  different, protected endpoint, and the whole design is read-only on purpose.
- Delivery is not this integration's business anyway. Whether the reminder goes
  to your own phone to paste into the Rover app, or by SMS to a sitter whose
  number you already have, is a choice with privacy consequences that belongs to
  you and to whichever notify service you already trust.

So this composes the words - the part that is easy to do badly - and an
automation decides where they go.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ARRIVAL,
    ATTR_CODE,
    ATTR_EXTRA_NOTE,
    ATTR_SERVICE_TYPE,
    ATTR_SITTER,
    DOMAIN,
    SERVICE_COMPOSE_ACCESS_MESSAGE,
)
from .coordinator import RoverCoordinator
from .message import compose_message, requires_house_access

COMPOSE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CODE): cv.string,
        vol.Optional(ATTR_SITTER): cv.string,
        vol.Optional(ATTR_SERVICE_TYPE): cv.string,
        # A datetime for a normal booking; a plain date so that an all-day
        # calendar event, which is how people record "sometime Tuesday", is not
        # rejected.
        #
        # Date first, and that order is load-bearing: `cv.datetime` accepts a
        # date-only string and quietly returns midnight, which would word an
        # all-day visit as "at 12am tomorrow". Trying the date first keeps "no
        # time given" distinguishable from "midnight".
        vol.Optional(ATTR_ARRIVAL): vol.Any(cv.date, cv.datetime),
        vol.Optional(ATTR_EXTRA_NOTE): cv.string,
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's services.

    Registered for the integration rather than per config entry, so the service
    exists to be called even while the entry is waiting on a fresh cookie.
    """

    async def async_compose(call: ServiceCall) -> ServiceResponse:
        """Compose a door-code reminder and return it."""
        sitter, service_type = _booking_defaults(
            hass,
            call.data.get(ATTR_SITTER),
            call.data.get(ATTR_SERVICE_TYPE),
        )
        arrival: datetime | date | None = call.data.get(ATTR_ARRIVAL)

        return {
            "message": compose_message(
                code=call.data[ATTR_CODE],
                sitter=sitter,
                service_type=service_type,
                arrival=arrival,
                extra_note=call.data.get(ATTR_EXTRA_NOTE),
            ),
            "sitter": sitter,
            "service_type": service_type,
            "requires_house_access": requires_house_access(service_type),
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_COMPOSE_ACCESS_MESSAGE,
        async_compose,
        schema=COMPOSE_SCHEMA,
        # ONLY, not OPTIONAL: a call that discards the response has done nothing
        # at all, and failing loudly is kinder than composing into the void.
        supports_response=SupportsResponse.ONLY,
    )


def _booking_defaults(
    hass: HomeAssistant,
    sitter: str | None,
    service_type: str | None,
) -> tuple[str | None, str | None]:
    """Fill in whatever the caller left out from the newest booking.

    Both stay None when there is nothing to read - no loaded entry, or a poll that
    has not landed yet. The message degrades to "Hi! ... before your visit", which
    is still a usable thing to send, rather than an error in the middle of somebody
    getting ready to leave the house.
    """
    if sitter and service_type:
        return sitter, service_type

    coordinator = _loaded_coordinator(hass)
    data = coordinator.data if coordinator else None
    if data is None:
        return sitter, service_type

    return sitter or data.latest_sitter, service_type or data.latest_service_type


def _loaded_coordinator(hass: HomeAssistant) -> RoverCoordinator | None:
    """Return the coordinator of the one loaded entry, if there is one.

    Singular on purpose: the config flow keys its unique ID off the domain, so this
    integration holds one Rover account per Home Assistant. If that limit is ever
    lifted, this is one of the places that has to grow a target selector.
    """
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        coordinator: Any = entry.runtime_data
        if isinstance(coordinator, RoverCoordinator):
            return coordinator
    return None
