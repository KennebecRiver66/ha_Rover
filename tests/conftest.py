"""Shared fixtures for the Rover Client tests.

Everything in here is fake. There is no real cookie, no real sitter and no real
account in this test suite, and there must never be one: the cookie is a
full-access credential and the sitter names are someone's neighbours. The fixtures
below are deliberately, obviously invented.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rover_client.const import CONF_COOKIE, DOMAIN
from homeassistant.core import HomeAssistant

# A cookie that has the right SHAPE and is obviously not real. Several pairs,
# because the config flow rejects a single pair as a partial paste.
FAKE_COOKIE = (
    "__cf_bm=fake-cf-value; csrftoken=fake-csrf-token; "
    "sessionid=fake-session-id; roverid=fake-rover-id"
)
FAKE_NEW_COOKIE = (
    "__cf_bm=fake-cf-value-2; csrftoken=fake-csrf-token-2; "
    "sessionid=fake-session-id-2; roverid=fake-rover-id-2"
)

# Fake sitters. Any resemblance to a real dog walker is unintended.
SITTER_ONE = "Testsitter"
SITTER_TWO = "Examplesitter"


def conversations_payload() -> dict[str, Any]:
    """Return a realistic conversations response.

    Shaped after the real endpoint - `results` newest first, sitter under
    `provider.first_name`, `stay_meta` carrying locations and an itinerary URL but
    no times - because a parser test against a tidied-up payload proves nothing
    about the payload the parser actually meets.
    """
    return {
        "count": 3,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": 111111,
                "service_type": "overnight-boarding",
                "provider": {
                    "id": 222222,
                    "first_name": SITTER_ONE,
                    "short_name": f"{SITTER_ONE} T.",
                },
                "request": None,
                "stay_meta": {
                    "start_location": "Springfield, ZZ",
                    "end_location": "Springfield, ZZ",
                    "itinerary_url": "/account/stays/111111/itinerary/",
                },
                "events": [{"id": 1, "type": "message"}],
            },
            {
                "id": 111112,
                "service_type": "dog-walking",
                "provider": {
                    "id": 222223,
                    "first_name": SITTER_TWO,
                    "short_name": f"{SITTER_TWO} E.",
                },
                "request": None,
                "stay_meta": None,
                "events": [],
            },
            {
                # Same sitter again, older booking. First occurrence must win.
                "id": 111113,
                "service_type": "drop-in-visit",
                "provider": {
                    "id": 222222,
                    "first_name": SITTER_ONE,
                },
                "request": None,
                "stay_meta": None,
                "events": [],
            },
        ],
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Load custom_components/rover_client in every test."""
    yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Stop the config flow tests from setting the integration up for real."""
    with patch(
        "custom_components.rover_client.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def mock_conversations() -> Generator[AsyncMock]:
    """Patch the one network call the integration makes."""
    with patch(
        "custom_components.rover_client.api.RoverClient.async_get_conversations",
        return_value=conversations_payload(),
    ) as mock:
        yield mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry holding the fake cookie."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Rover",
        data={CONF_COOKIE: FAKE_COOKIE},
        unique_id=DOMAIN,
        entry_id="01jfakeentryid0000000000",
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_conversations: AsyncMock,
) -> MockConfigEntry:
    """Set the integration up with a successful poll."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
