"""Tests for the config, reauth and options flows.

The flow is where a stranger's install succeeds or fails, so it is covered in more
detail than anything else here: the happy path, every error the form can show, and
the reauth path that must update the entry IN PLACE - if reauth ever created a new
entry instead, every entity ID would change and every automation referencing them
would quietly break.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rover_client.api import (
    RoverAuthError,
    RoverBlockedError,
    RoverConnectionError,
)
from custom_components.rover_client.const import (
    CONF_COOKIE,
    CONF_SCAN_INTERVAL_HOURS,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import FAKE_COOKIE, FAKE_NEW_COOKIE, conversations_payload

API = "custom_components.rover_client.api.RoverClient.async_get_conversations"


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """A good cookie produces one entry holding that cookie."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    with patch(API, return_value=conversations_payload()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: FAKE_COOKIE}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Rover"
    assert result["data"] == {CONF_COOKIE: FAKE_COOKIE}
    assert result["result"].unique_id == DOMAIN
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_flow_normalises_the_paste(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """A header pasted with its name, quotes and devtools line wrapping still works.

    This is the single most common paste, and repairing it silently is the whole
    point of the normaliser - the user should never be told off for copying the
    header the way devtools offers it.
    """
    messy = '  "Cookie: __cf_bm=fake-cf-value;\n  csrftoken=fake-csrf\n-token;  "  '

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(API, return_value=conversations_payload()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: messy}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_COOKIE: "__cf_bm=fake-cf-value; csrftoken=fake-csrf-token"
    }


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (RoverAuthError("signed out"), "invalid_auth"),
        (RoverBlockedError("challenge"), "blocked"),
        (RoverConnectionError("socket"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_api_errors(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    side_effect: Exception,
    expected_error: str,
) -> None:
    """Each failure from the API maps to its own message, and the form stays open."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(API, side_effect=side_effect):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: FAKE_COOKIE}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": expected_error}

    # Recovering in the same flow must work, rather than forcing a restart.
    with patch(API, return_value=conversations_payload()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: FAKE_COOKIE}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    ("pasted", "expected_error"),
    [
        ("sessionid=fake-session-id", "partial_cookie"),
        ("Cookie: sessionid=fake-session-id", "partial_cookie"),
        ("this is not a cookie at all", "invalid_cookie_format"),
        ("   ", "invalid_cookie_format"),
    ],
)
async def test_user_flow_rejects_bad_pastes_without_calling_rover(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    pasted: str,
    expected_error: str,
) -> None:
    """A malformed paste is diagnosed locally, not by a round trip to Rover.

    Both the specific message and the absence of the call matter: telling someone
    "Rover rejected your cookie" when they pasted one row of a table sends them
    looking in the wrong place, and the request would be a pointless authenticated
    hit on a bot-protected endpoint.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(API, return_value=conversations_payload()) as api:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: pasted}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}
    assert api.call_count == 0


async def test_user_flow_single_account(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_setup_entry: AsyncMock
) -> None:
    """A second attempt aborts: the unique ID is the domain, one account per HA."""
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(API, return_value=conversations_payload()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: FAKE_NEW_COOKIE}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_entry_in_place(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_conversations: AsyncMock,
) -> None:
    """Reauth replaces the cookie and keeps the entry, its ID and its entities."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entities_before = sorted(
        state.entity_id for state in hass.states.async_all("sensor")
    )
    assert entities_before

    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_COOKIE: FAKE_NEW_COOKIE}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"

    assert config_entry.data[CONF_COOKIE] == FAKE_NEW_COOKIE
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert hass.config_entries.async_entries(DOMAIN)[0].entry_id == (
        config_entry.entry_id
    )
    assert (
        sorted(state.entity_id for state in hass.states.async_all("sensor"))
        == entities_before
    )


async def test_reauth_shows_errors_and_keeps_old_cookie(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_conversations: AsyncMock,
) -> None:
    """A bad replacement cookie is refused without discarding the saved one."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await config_entry.start_reauth_flow(hass)

    with patch(API, side_effect=RoverAuthError("still signed out")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: FAKE_NEW_COOKIE}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert config_entry.data[CONF_COOKIE] == FAKE_COOKIE


async def test_options_flow_sets_interval(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The saved interval reaches the coordinator."""
    result = await hass.config_entries.options.async_init(
        setup_integration.entry_id
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL_HOURS: 12}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_integration.options == {CONF_SCAN_INTERVAL_HOURS: 12}
    coordinator = setup_integration.runtime_data
    assert coordinator.update_interval.total_seconds() == 12 * 3600


async def test_options_flow_refuses_a_tight_poll(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The one-hour floor is a rule, not a hint: the selector rejects less."""
    result = await hass.config_entries.options.async_init(
        setup_integration.entry_id
    )

    with pytest.raises(vol.Invalid, match=CONF_SCAN_INTERVAL_HOURS):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL_HOURS: 0.25}
        )

    assert CONF_SCAN_INTERVAL_HOURS not in setup_integration.options
