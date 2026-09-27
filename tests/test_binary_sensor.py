"""Tests for the house-access binary sensor.

This entity is the guard on a door code, so the cases that matter are the ones
where it must be OFF: boarding at the sitter's own house, a service type Rover has
renamed, and any moment when the integration does not actually know.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rover_client.api import RoverBlockedError
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from .conftest import SITTER_ONE, SITTER_TWO

API = "custom_components.rover_client.api.RoverClient.async_get_conversations"
ACCESS = "binary_sensor.rover_house_access_needed"


def payload(*bookings: tuple[str, str]) -> dict[str, Any]:
    """Return a conversations payload for (sitter, service type) pairs, newest first."""
    return {
        "count": len(bookings),
        "results": [
            {
                "id": 900000 + index,
                "service_type": service_type,
                "provider": {"id": 800000 + index, "first_name": sitter},
                "request": None,
                "stay_meta": None,
                "events": [],
            }
            for index, (sitter, service_type) in enumerate(bookings)
        ],
    }


async def test_off_for_a_boarding_stay(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The shared fixture's newest booking is boarding, which needs no code."""
    assert hass.states.get(ACCESS).state == STATE_OFF


async def test_on_for_a_drop_in(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A drop-in happens at your house, so the door has to open."""
    with patch(API, return_value=payload((SITTER_ONE, "drop-in-visit"))):
        await setup_integration.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(ACCESS).state == STATE_ON


async def test_on_for_a_walk(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """So does a walk: the dog has to be collected from inside."""
    with patch(API, return_value=payload((SITTER_TWO, "dog-walking"))):
        await setup_integration.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(ACCESS).state == STATE_ON


async def test_off_for_a_service_nobody_has_seen_before(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """An unrecognised slug reads as off. Failing closed is the whole design."""
    with patch(API, return_value=payload((SITTER_ONE, "rover-invented-this"))):
        await setup_integration.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(ACCESS).state == STATE_OFF


async def test_attributes_name_the_booking_and_the_sitters(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The attributes answer "who needs a code this week", which the state cannot."""
    with patch(
        API,
        return_value=payload(
            (SITTER_ONE, "drop-in-visit"),
            (SITTER_TWO, "overnight-boarding"),
        ),
    ):
        await setup_integration.runtime_data.async_refresh()
        await hass.async_block_till_done()

    attributes = hass.states.get(ACCESS).attributes

    assert attributes["latest_service_type"] == "drop-in-visit"
    assert attributes["latest_sitter"] == SITTER_ONE
    assert attributes["sitters_needing_access"] == [SITTER_ONE]


async def test_unavailable_while_blocked(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A stale "nobody needs the door" is the state that suppresses a reminder.

    So when the session is bad this entity goes unavailable rather than reporting
    off, which an automation would read as "no code needed today".
    """
    with patch(API, side_effect=RoverBlockedError("challenge page")):
        await setup_integration.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(ACCESS).state == STATE_UNAVAILABLE
