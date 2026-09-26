"""Tests for entry setup, the repair issue and diagnostics."""

from __future__ import annotations

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.rover_client.api import RoverAuthError
from custom_components.rover_client.const import (
    CONF_COOKIE,
    DOMAIN,
    ISSUE_SESSION_EXPIRED,
)
from custom_components.rover_client.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .conftest import FAKE_COOKIE, conversations_payload

API = "custom_components.rover_client.api.RoverClient.async_get_conversations"


def issue_id(entry: MockConfigEntry) -> str:
    """Return the repair issue ID for an entry."""
    return f"{ISSUE_SESSION_EXPIRED}_{entry.entry_id}"


async def test_setup_and_unload(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A good cookie loads, and unloading puts the entry back to NOT_LOADED."""
    assert setup_integration.state is ConfigEntryState.LOADED
    assert setup_integration.runtime_data is not None

    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert setup_integration.state is ConfigEntryState.NOT_LOADED


async def test_dead_session_raises_a_repair(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """An expired cookie shows up on the Repairs dashboard, not just in Settings.

    The reauth card is correct but quiet, and this is a failure that happens every
    few weeks. A silent stop is the worst outcome for a household that has stopped
    getting announcements about the dog.
    """
    config_entry.add_to_hass(hass)

    with patch(API, side_effect=RoverAuthError("session rejected")):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id(config_entry))
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR
    assert issue.translation_key == ISSUE_SESSION_EXPIRED
    assert issue.translation_placeholders == {"title": "Rover"}


async def test_repair_clears_when_the_session_works_again(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A successful poll takes the repair away again."""
    config_entry.add_to_hass(hass)

    with patch(API, side_effect=RoverAuthError("session rejected")):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id(config_entry))

    with patch(API, return_value=conversations_payload()):
        await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id(config_entry)) is None


async def test_removing_the_entry_removes_the_repair(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Deleting the integration does not leave a repair behind to haunt Settings."""
    config_entry.add_to_hass(hass)

    with patch(API, side_effect=RoverAuthError("session rejected")):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id(config_entry))

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id(config_entry)) is None


async def test_diagnostics_hide_the_cookie_and_the_sitters(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Diagnostics must stay safe to paste into a public issue.

    Two secrets, two different reasons: the cookie is a full-access credential, and
    the sitter names are someone else's personal data. Both are asserted on because
    this file gets extended, and the next field added is the one that leaks.
    """
    diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)
    serialised = str(diagnostics)

    assert FAKE_COOKIE not in serialised
    assert "fake-csrf-token" not in serialised
    assert "Testsitter" not in serialised
    assert "Examplesitter" not in serialised

    assert diagnostics["entry"]["redacted"] == [CONF_COOKIE]
    assert diagnostics["cookie"] == {
        "count": 4,
        "names": ["__cf_bm", "csrftoken", "roverid", "sessionid"],
    }
    assert diagnostics["data"]["sitter_count"] == 2
    assert diagnostics["data"]["service_types_seen"] == [
        "dog-walking",
        "overnight-boarding",
    ]
