"""Sensors for Rover Client."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SESSION_SIGNED_IN
from .coordinator import RoverConfigEntry, RoverCoordinator, RoverData


@dataclass(frozen=True, kw_only=True)
class RoverSensorDescription(SensorEntityDescription):
    """Describes a Rover sensor."""

    value_fn: Callable[[RoverData], StateType]


SENSORS: tuple[RoverSensorDescription, ...] = (
    RoverSensorDescription(
        key="session",
        translation_key="session",
        # An enum would be tidier, but the set of failure words is the thing most
        # likely to grow as new block styles appear, and changing enum options is
        # a breaking change for anyone's automations.
        value_fn=lambda data: data.session_state,
    ),
    RoverSensorDescription(
        key="latest_service_type",
        translation_key="latest_service_type",
        value_fn=lambda data: data.latest_service_type,
    ),
    RoverSensorDescription(
        key="conversation_count",
        translation_key="conversation_count",
        native_unit_of_measurement="conversations",
        value_fn=lambda data: data.conversation_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoverConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Rover sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        RoverSensor(coordinator, entry, description) for description in SENSORS
    )


class RoverSensor(CoordinatorEntity[RoverCoordinator], SensorEntity):
    """A sensor backed by the Rover conversations poll."""

    _attr_has_entity_name = True
    entity_description: RoverSensorDescription

    def __init__(
        self,
        coordinator: RoverCoordinator,
        entry: RoverConfigEntry,
        description: RoverSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Rover",
            manufacturer="Rover.com",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.rover.com/members/",
        )

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Expose the per-sitter service-type map on the latest-type sensor.

        As attributes rather than one packed string: the old YAML version encoded
        this as 'Alex=overnight-boarding;Erin=dog-walking' purely because a sensor
        state is capped at 255 characters. Attributes have no such limit, so
        consumers can index a real mapping instead of parsing a string.
        """
        if (
            self.entity_description.key != "latest_service_type"
            or self.coordinator.data is None
        ):
            return None
        data = self.coordinator.data
        attrs: dict[str, str] = dict(data.service_types)
        if data.latest_sitter:
            attrs["latest_sitter"] = data.latest_sitter
        return attrs or None

    @property
    def available(self) -> bool:
        """Session state stays readable even when the session itself is bad.

        The other sensors go unavailable, because a stale service type presented as
        current is worse than no value. The session sensor is the one that must keep
        reporting - it is how you find out WHY the rest went quiet.
        """
        if self.entity_description.key == "session":
            return self.coordinator.data is not None
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.session_state == SESSION_SIGNED_IN
        )
