"""Diagnostics for Rover Client."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_COOKIE
from .cookie import cookie_names, count_cookies
from .coordinator import RoverConfigEntry

# The cookie IS the credential - it grants full access to the Rover account.
# Diagnostics get pasted into public issue trackers, so this redaction is the
# difference between a useful bug report and an account handover.
TO_REDACT = {CONF_COOKIE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RoverConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, with the cookie removed."""
    coordinator = entry.runtime_data
    data = coordinator.data
    cookie = entry.data.get(CONF_COOKIE, "")

    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "data_keys": sorted(entry.data),
            "options": dict(entry.options),
            "redacted": sorted(TO_REDACT),
        },
        # Names and a count, never values. "You pasted one cookie, not the header"
        # is the most common setup failure, and it is answerable from the shape of
        # the header alone - so the shape is reported and the secret is not.
        "cookie": {
            "count": count_cookies(cookie),
            "names": cookie_names(cookie),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        "data": {
            "session_state": data.session_state if data else None,
            "conversation_count": data.conversation_count if data else None,
            "latest_service_type": data.latest_service_type if data else None,
            # Sitter first names are personal data, so report only how many were
            # seen and which service types appeared - enough to debug the parser
            # without publishing who walks the dogs.
            "sitter_count": len(data.service_types) if data else None,
            "service_types_seen": (
                sorted(set(data.service_types.values())) if data else None
            ),
            "detail": data.detail if data else None,
        },
    }
