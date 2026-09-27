"""Tests for the sensors, including the availability rule that is easy to break.

`sensor.rover_session` staying available while the others go unavailable is a
deliberate design decision, not an accident of the base class, so it is pinned
here: it is the sensor that explains why the rest went quiet.
"""

from __future__ import annotations

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rover_client.api import (
    RoverAuthError,
    RoverBlockedError,
    RoverConnectionError,
)
from custom_components.rover_client.const import (
    DOMAIN,
    SESSION_BLOCKED,
    SESSION_ERROR,
    SESSION_NOT_SIGNED_IN,
    SESSION_SIGNED_IN,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import SITTER_ONE, SITTER_TWO, conversations_payload

API = "custom_components.rover_client.api.RoverClient.async_get_conversations"

SESSION = "sensor.rover_session"
LATEST = "sensor.rover_latest_service_type"
COUNT = "sensor.rover_conversations"
ACCESS = "binary_sensor.rover_house_access_needed"


async def test_entities_and_their_ids(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The integration's entities exist under the expected IDs.

    The IDs are part of the contract: `has_entity_name` plus a service device is
    what produces `sensor.rover_*`, and anyone's automations are written against
    those exact strings.
    """
    assert hass.states.get(SESSION).state == SESSION_SIGNED_IN
    assert hass.states.get(LATEST).state == "overnight-boarding"
    assert hass.states.get(COUNT).state == "3"

    registry = er.async_get(hass)
    assert {
        entry.entity_id: entry.unique_id
        for entry in er.async_entries_for_config_entry(
            registry, setup_integration.entry_id
        )
    } == {
        SESSION: f"{setup_integration.entry_id}_session",
        LATEST: f"{setup_integration.entry_id}_latest_service_type",
        COUNT: f"{setup_integration.entry_id}_conversation_count",
        ACCESS: f"{setup_integration.entry_id}_house_access_needed",
    }


async def test_one_service_device(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Every entity hangs off a single service device."""
    devices = dr.async_entries_for_config_entry(
        dr.async_get(hass), setup_integration.entry_id
    )

    assert len(devices) == 1
    assert devices[0].identifiers == {(DOMAIN, setup_integration.entry_id)}
    assert devices[0].entry_type is dr.DeviceEntryType.SERVICE


async def test_sitter_map_is_exposed_as_attributes(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The per-sitter map is attributes, not a packed string."""
    attributes = hass.states.get(LATEST).attributes

    assert attributes[SITTER_ONE] == "overnight-boarding"
    assert attributes[SITTER_TWO] == "dog-walking"
    assert attributes["latest_sitter"] == SITTER_ONE


async def test_session_sensor_survives_a_block(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """When blocked, the session sensor reports why and the others stand down."""
    with patch(API, side_effect=RoverBlockedError("challenge page")):
        await setup_integration.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(SESSION).state == SESSION_BLOCKED
    assert hass.states.get(LATEST).state == STATE_UNAVAILABLE
    assert hass.states.get(COUNT).state == STATE_UNAVAILABLE


async def test_session_sensor_reports_a_network_failure(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """After a failed poll the session sensor says so instead of the old value.

    The trap this guards is specific: a failed update leaves the coordinator's data
    at the last SUCCESSFUL poll, so reading it would have the one diagnostic sensor
    cheerfully report "Signed in" through an outage that started days ago.
    """
    with patch(API, side_effect=RoverConnectionError("no route")):
        await setup_integration.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(SESSION).state == SESSION_ERROR
    assert hass.states.get(LATEST).state == STATE_UNAVAILABLE

    with patch(API, return_value=conversations_payload()):
        await setup_integration.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(SESSION).state == SESSION_SIGNED_IN
    assert hass.states.get(LATEST).state == "overnight-boarding"


async def test_session_sensor_reports_a_rejected_cookie(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A dead cookie reads as `not_signed_in`, not as the last good value."""
    with patch(API, side_effect=RoverAuthError("session rejected")):
        await setup_integration.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(SESSION).state == SESSION_NOT_SIGNED_IN
    assert hass.states.get(LATEST).state == STATE_UNAVAILABLE


async def test_unload_removes_the_entities(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Unloading cleans up after itself."""
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(SESSION).state == STATE_UNAVAILABLE
