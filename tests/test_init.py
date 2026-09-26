"""Tests for entry setup, the repair issue and diagnostics."""

from __future__ import annotations

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.rover_client.api import RoverAuthError, RoverBlockedError
from custom_components.rover_client.const import (
    BLOCKED_POLLS_BEFORE_REPAIR,
    CONF_COOKIE,
    DOMAIN,
    ISSUE_BLOCKED,
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
    """Return the blocked-repair issue ID for an entry."""
    return f"{ISSUE_BLOCKED}_{entry.entry_id}"


async def block_repeatedly(
    hass: HomeAssistant, entry: MockConfigEntry, polls: int
) -> None:
    """Poll `polls` times with Rover answering a challenge every time."""
    with patch(API, side_effect=RoverBlockedError("challenge page")):
        for _ in range(polls):
            await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A good cookie loads, and unloading puts the entry back to NOT_LOADED."""
    assert setup_integration.state is ConfigEntryState.LOADED
    assert setup_integration.runtime_data is not None

    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert setup_integration.state is ConfigEntryState.NOT_LOADED


async def test_dead_session_leaves_the_repair_to_home_assistant(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """An expired cookie is Home Assistant's repair to raise, and it does.

    Pinned as a test because it is the reason this integration does not raise one of
    its own. Core creates `config_entry_reauth_*` whenever ConfigEntryAuthFailed
    starts a reauth flow, and that card opens the reauth dialog directly - a second
    card of ours would be the same news in worse words. If core ever stops doing
    this, this test fails and the decision gets revisited.
    """
    config_entry.add_to_hass(hass)

    with patch(API, side_effect=RoverAuthError("session rejected")):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    registry = ir.async_get(hass)
    assert registry.async_get_issue(
        "homeassistant", f"config_entry_reauth_{DOMAIN}_{config_entry.entry_id}"
    )
    assert registry.async_get_issue(DOMAIN, issue_id(config_entry)) is None


async def test_one_challenge_raises_nothing(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A single challenge is routine and clears itself - no repair for that."""
    await block_repeatedly(hass, setup_integration, BLOCKED_POLLS_BEFORE_REPAIR - 1)

    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, issue_id(setup_integration)) is None
    )


async def test_a_run_of_challenges_raises_a_repair(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A persistent block is the silent failure nothing else reports.

    Being blocked is deliberately reported as a state rather than an exception, so
    Home Assistant sees a healthy integration and says nothing. Data has stopped all
    the same, and a household that stopped getting announcements about the dog
    deserves to be told why.
    """
    await block_repeatedly(hass, setup_integration, BLOCKED_POLLS_BEFORE_REPAIR)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id(setup_integration))
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_key == ISSUE_BLOCKED
    assert issue.translation_placeholders == {
        "title": "Rover",
        "polls": str(BLOCKED_POLLS_BEFORE_REPAIR),
    }


async def test_repair_clears_when_a_poll_gets_through(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """One successful poll retires the repair and forgives the streak."""
    await block_repeatedly(hass, setup_integration, BLOCKED_POLLS_BEFORE_REPAIR)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id(setup_integration))

    with patch(API, return_value=conversations_payload()):
        await setup_integration.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, issue_id(setup_integration)) is None
    )

    # And the count restarts, rather than the next single challenge re-raising it.
    await block_repeatedly(hass, setup_integration, 1)
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, issue_id(setup_integration)) is None
    )


async def test_removing_the_entry_removes_the_repair(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Deleting the integration does not leave a repair behind to haunt Settings."""
    await block_repeatedly(hass, setup_integration, BLOCKED_POLLS_BEFORE_REPAIR)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id(setup_integration))

    assert await hass.config_entries.async_remove(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, issue_id(setup_integration)) is None
    )


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
