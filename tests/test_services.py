"""Tests for the compose_access_message service."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rover_client.const import (
    DOMAIN,
    SERVICE_COMPOSE_ACCESS_MESSAGE,
)
from custom_components.rover_client.message import TEMPLATES, compose_message
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from .conftest import SITTER_ONE

FAKE_CODE = "135790"


async def compose(hass: HomeAssistant, **data: object) -> dict:
    """Call the service and return its response."""
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_COMPOSE_ACCESS_MESSAGE,
        data,
        blocking=True,
        return_response=True,
    )
    assert response is not None
    return response


async def test_the_service_exists_without_a_config_entry(
    hass: HomeAssistant,
) -> None:
    """Registered for the integration, not for an entry.

    Which is what lets it be called while the entry is waiting on a fresh cookie -
    a dead cookie should not also take away the ability to word a reminder.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_COMPOSE_ACCESS_MESSAGE)

    response = await compose(hass, code=FAKE_CODE)

    assert FAKE_CODE in response["message"]
    assert response["sitter"] is None
    assert response["requires_house_access"] is False


async def test_defaults_come_from_the_newest_booking(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """With an entry loaded, the sitter and service need not be passed in."""
    response = await compose(hass, code=FAKE_CODE)

    assert response["sitter"] == SITTER_ONE
    # The fixture's newest booking is boarding, at the sitter's own house.
    assert response["service_type"] == "overnight-boarding"
    assert response["requires_house_access"] is False
    assert SITTER_ONE in response["message"]


async def test_the_reply_reports_when_access_is_needed(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """An explicit service type overrides the booking, and drives the flag."""
    response = await compose(
        hass,
        code=FAKE_CODE,
        sitter="Examplesitter",
        service_type="dog-walking",
    )

    assert response["requires_house_access"] is True
    assert response["service_type"] == "dog-walking"
    assert "Examplesitter" in response["message"]
    assert "your walk" in response["message"]


async def test_an_arrival_time_is_worded_into_the_message(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A datetime arrives from a calendar trigger as a string and is parsed."""
    response = await compose(
        hass,
        code=FAKE_CODE,
        service_type="drop-in-visit",
        arrival="2026-09-29 15:00:00",
    )

    assert "your drop-in at 3pm" in response["message"]


async def test_an_all_day_event_is_accepted_as_a_date(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """All-day calendar events hand over a date, not a datetime.

    Worth a test because rejecting it would make the blueprint fail for anyone who
    records visits as "sometime Tuesday".
    """
    tomorrow = dt_util.now().date() + timedelta(days=1)
    response = await compose(
        hass,
        code=FAKE_CODE,
        service_type="dog-walking",
        arrival=tomorrow.isoformat(),
    )

    assert "your walk tomorrow" in response["message"]


async def test_arrival_accepts_real_date_objects(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A template can also hand over objects rather than strings."""
    for arrival in (datetime(2026, 9, 29, 15, 0), date(2026, 9, 29)):
        response = await compose(
            hass, code=FAKE_CODE, service_type="dog-walking", arrival=arrival
        )
        assert FAKE_CODE in response["message"]


async def test_an_extra_note_is_appended(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The user's own sentence survives the trip through the service."""
    response = await compose(
        hass,
        code=FAKE_CODE,
        service_type="dog-walking",
        extra_note="Treats are in the tin on the counter.",
    )

    assert response["message"].endswith("Treats are in the tin on the counter.")


async def test_the_code_is_required(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A reminder without a code is not worth sending."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COMPOSE_ACCESS_MESSAGE,
            {"sitter": SITTER_ONE},
            blocking=True,
            return_response=True,
        )


async def test_an_unparseable_arrival_is_rejected_rather_than_guessed(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """"Some time this afternoon" cannot be turned into a time, so it errors.

    Better than silently dropping it: a message that quietly loses the time is one
    the sitter reads as "let yourself in whenever".
    """
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COMPOSE_ACCESS_MESSAGE,
            {"code": FAKE_CODE, "arrival": "some time this afternoon"},
            blocking=True,
            return_response=True,
        )


async def test_the_wording_is_one_of_the_variants(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The service composes; it does not improvise."""
    expected = {
        compose_message(
            code=FAKE_CODE,
            sitter=SITTER_ONE,
            service_type="dog-walking",
            variant=index,
        )
        for index in range(len(TEMPLATES))
    }

    response = await compose(
        hass, code=FAKE_CODE, sitter=SITTER_ONE, service_type="dog-walking"
    )

    assert response["message"] in expected
