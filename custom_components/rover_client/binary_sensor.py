"""Binary sensor for Rover Client."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SESSION_SIGNED_IN
from .coordinator import RoverConfigEntry, RoverCoordinator
from .message import requires_house_access


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoverConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Rover binary sensor."""
    async_add_entities([RoverHouseAccessBinarySensor(entry.runtime_data, entry)])


class RoverHouseAccessBinarySensor(
    CoordinatorEntity[RoverCoordinator], BinarySensorEntity
):
    """On when the newest booking is a service performed at the owner's home.

    Exists so that an automation handing out a door code has a condition to check
    that is not a string comparison against an undocumented slug. Boarding and
    day care happen at the sitter's house and must not trigger one; walks,
    drop-ins and house-sitting must.

    It describes the NEWEST booking, not the next one, for the same reason
    `sensor.rover_latest_service_type` does: Rover's conversations endpoint carries
    no booking times, so "next" is not a thing this integration can know.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "house_access_needed"

    def __init__(
        self, coordinator: RoverCoordinator, entry: RoverConfigEntry
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_house_access_needed"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Rover",
            manufacturer="Rover.com",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.rover.com/members/",
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether the newest booking needs someone inside the house."""
        if self.coordinator.data is None:
            return None
        return requires_house_access(self.coordinator.data.latest_service_type)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Name the booking behind the state, and every sitter who needs access.

        The per-sitter list matters when several sitters are booked at once: the
        state answers "does the newest booking need the door open", which is not
        the same question as "who should be sent a code this week".
        """
        data = self.coordinator.data
        if data is None:
            return None
        return {
            "latest_service_type": data.latest_service_type,
            "latest_sitter": data.latest_sitter,
            "sitters_needing_access": sorted(
                sitter
                for sitter, service_type in data.service_types.items()
                if requires_house_access(service_type)
            ),
        }

    @property
    def available(self) -> bool:
        """Unavailable whenever the session is not good.

        Same rule as the service-type sensor and for the same reason: a stale
        "nobody needs the door" is worse than no answer, because it is the state
        that suppresses a reminder.
        """
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.session_state == SESSION_SIGNED_IN
        )
