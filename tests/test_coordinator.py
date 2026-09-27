"""Tests for the coordinator: parsing, failure translation and the poll interval.

The parser reads an undocumented API that can change without notice, so the tests
that matter most are the ones proving it degrades instead of raising. A parser that
throws takes the whole integration offline; a parser that returns None for a field
loses one sensor value.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rover_client.api import (
    RoverAuthError,
    RoverBlockedError,
    RoverConnectionError,
)
from custom_components.rover_client.const import (
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_SCAN_INTERVAL_HOURS,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
    SESSION_BLOCKED,
    SESSION_SIGNED_IN,
)
from custom_components.rover_client.coordinator import RoverCoordinator, scan_interval
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from .conftest import SITTER_ONE, SITTER_TWO, conversations_payload

API = "custom_components.rover_client.api.RoverClient.async_get_conversations"


def test_parse_realistic_payload() -> None:
    """A realistic payload yields the state, the count and the per-sitter map."""
    data = RoverCoordinator._parse(conversations_payload())

    assert data.session_state == SESSION_SIGNED_IN
    assert data.conversation_count == 3
    assert data.latest_service_type == "overnight-boarding"
    assert data.latest_sitter == SITTER_ONE
    # Newest booking per sitter wins, so the sitter's older drop-in visit does not
    # overwrite their overnight boarding.
    assert data.service_types == {
        SITTER_ONE: "overnight-boarding",
        SITTER_TWO: "dog-walking",
    }
    assert data.detail is None


def test_parse_counts_every_conversation_but_reads_only_the_first_page() -> None:
    """The count covers all results; service types stop at the scan depth."""
    payload = conversations_payload()
    payload["results"] = [
        {
            "service_type": f"service-{index}",
            "provider": {"first_name": f"Sitter{index}"},
        }
        for index in range(25)
    ]

    data = RoverCoordinator._parse(payload)

    assert data.conversation_count == 25
    assert len(data.service_types) == 10
    assert data.latest_service_type == "service-0"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="empty object"),
        pytest.param({"results": None}, id="results null"),
        pytest.param({"results": "nonsense"}, id="results not a list"),
        pytest.param({"results": [None, 42, "text"]}, id="entries not objects"),
        pytest.param({"results": [{}]}, id="entry with no fields"),
        pytest.param(
            {"results": [{"service_type": None, "provider": None}]},
            id="fields explicitly null",
        ),
        pytest.param(
            {"results": [{"service_type": "dog-walking", "provider": "Testsitter"}]},
            id="provider reshaped to a string",
        ),
        pytest.param(
            {"results": [{"service_type": 7, "provider": {"first_name": 9}}]},
            id="fields retyped to numbers",
        ),
    ],
)
def test_parse_malformed_payloads_degrade(payload: dict[str, Any]) -> None:
    """Nothing malformed raises - the worst case is a missing value."""
    data = RoverCoordinator._parse(payload)

    assert data.session_state == SESSION_SIGNED_IN
    assert isinstance(data.conversation_count, int)
    assert data.latest_service_type in (None, "dog-walking", "7")
    assert isinstance(data.service_types, dict)


def test_parse_ignores_a_conversation_with_no_sitter() -> None:
    """A service type with no provider still sets the latest type, but no map entry."""
    data = RoverCoordinator._parse(
        {"results": [{"service_type": "overnight-boarding", "provider": {}}]}
    )

    assert data.latest_service_type == "overnight-boarding"
    assert data.latest_sitter is None
    assert data.service_types == {}


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A rejected cookie asks the user for a new one instead of retrying it."""
    config_entry.add_to_hass(hass)

    with patch(API, side_effect=RoverAuthError("signed out")):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(config_entry.domain)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_blocked_is_a_state_not_a_failure(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A bot challenge reports `blocked` and keeps the update marked successful.

    Raising here would mark every entity unavailable and throw away the one fact
    worth having, which is why the data went quiet.
    """
    coordinator: RoverCoordinator = setup_integration.runtime_data

    with patch(API, side_effect=RoverBlockedError("challenge page")):
        await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data.session_state == SESSION_BLOCKED
    assert coordinator.data.detail == "challenge page"
    assert coordinator.data.conversation_count == 0


async def test_connection_error_is_transient(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A socket error fails the update so it is retried, and nothing else."""
    coordinator: RoverCoordinator = setup_integration.runtime_data

    with patch(API, side_effect=RoverConnectionError("no route")):
        await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert not hass.config_entries.flow.async_progress_by_handler(
        setup_integration.domain
    )


async def test_failure_modes_raise_their_own_exceptions(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The three API errors translate to three different HA reactions."""
    coordinator: RoverCoordinator = setup_integration.runtime_data

    with (
        patch(API, side_effect=RoverAuthError("dead")),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await coordinator._async_update_data()

    with (
        patch(API, side_effect=RoverConnectionError("dead")),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    with patch(API, side_effect=RoverBlockedError("challenge")):
        data = await coordinator._async_update_data()
    assert data.session_state == SESSION_BLOCKED


@pytest.mark.parametrize(
    ("options", "expected_hours"),
    [
        pytest.param({}, DEFAULT_SCAN_INTERVAL_HOURS, id="unset"),
        pytest.param({CONF_SCAN_INTERVAL_HOURS: 24}, 24, id="lengthened"),
        pytest.param(
            {CONF_SCAN_INTERVAL_HOURS: 0.1}, MIN_SCAN_INTERVAL_HOURS, id="below floor"
        ),
        pytest.param(
            {CONF_SCAN_INTERVAL_HOURS: 10_000},
            MAX_SCAN_INTERVAL_HOURS,
            id="above ceiling",
        ),
        pytest.param(
            {CONF_SCAN_INTERVAL_HOURS: "not a number"},
            DEFAULT_SCAN_INTERVAL_HOURS,
            id="unusable",
        ),
    ],
)
def test_scan_interval_is_clamped(
    options: dict[str, Any], expected_hours: float
) -> None:
    """A stored interval is clamped, whatever wrote it.

    The floor is re-enforced away from the options form because the form is not the
    only thing that can write the value - a hand-edited .storage file can too, and
    a tight poll against a bot-protected endpoint is the one mistake with a cost
    the user cannot see or debug.
    """
    entry = MockConfigEntry(domain="rover_client", options=options)

    assert scan_interval(entry) == timedelta(hours=expected_hours)
