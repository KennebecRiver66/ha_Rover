"""The Rover Client integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, ISSUE_BLOCKED
from .coordinator import RoverConfigEntry, RoverCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: RoverConfigEntry) -> bool:
    """Set up Rover Client from a config entry."""
    coordinator = RoverCoordinator(hass, entry)

    # Raises ConfigEntryAuthFailed / ConfigEntryNotReady for us, so a bad cookie
    # surfaces as a reauth prompt at setup time rather than a broken entry.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RoverConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: RoverConfigEntry) -> None:
    """Take the blocked repair away with the entry that raised it.

    Not done on unload: an unload is usually half of a reload, and a repair that
    blinks out and back is worse than one that stays put.
    """
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_BLOCKED}_{entry.entry_id}")


async def _async_update_listener(hass: HomeAssistant, entry: RoverConfigEntry) -> None:
    """Reload when the cookie or the poll interval changes, so it takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)
