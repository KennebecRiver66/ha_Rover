"""Tests for the HTTP client, against the responses Rover actually returns.

The three-way split between "signed out", "challenged" and "broken" is decided
here, on evidence that is easy to get wrong: the challenge arrives as an HTTP 200
carrying HTML, and a signed-out response arrives as an HTTP 200 carrying
`{"detail": ...}`. Neither can be recognised from a status code, so both are
pinned with tests rather than left to a future reader's judgement.
"""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.rover_client.api import (
    RoverAuthError,
    RoverBlockedError,
    RoverClient,
    RoverConnectionError,
)
from custom_components.rover_client.const import (
    BASE_URL,
    CONVERSATIONS_PATH,
    USER_AGENT,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import FAKE_COOKIE, conversations_payload

URL = f"{BASE_URL}{CONVERSATIONS_PATH}"

CHALLENGE_PAGE = (
    "<!DOCTYPE html><html><head><title>Just a moment...</title></head>"
    "<body><div id='cf-browser-verification'></div></body></html>"
)


def client(hass: HomeAssistant) -> RoverClient:
    """Return a client using Home Assistant's shared session."""
    return RoverClient(async_get_clientsession(hass), FAKE_COOKIE)


async def test_returns_the_payload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A normal response comes back as the parsed object."""
    aioclient_mock.get(URL, json=conversations_payload())

    assert await client(hass).async_get_conversations() == conversations_payload()


async def test_sends_the_whole_header_set(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Every request carries the full header set, not a subset.

    A request missing half of them is a different and more obviously automated
    fingerprint than one sending all of them, which is the entire reason the
    headers are built in one place.
    """
    aioclient_mock.get(URL, json={"results": []})

    await client(hass).async_get_conversations()

    headers = aioclient_mock.mock_calls[0][3]
    assert headers["Cookie"] == FAKE_COOKIE
    assert headers["User-Agent"] == USER_AGENT
    assert headers["Accept"] == "application/json"
    assert headers["Referer"].startswith(BASE_URL)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(CHALLENGE_PAGE, id="full challenge page"),
        pytest.param("<html>Just a moment...</html>", id="title only"),
        pytest.param("<div id=cf-browser-verification></div>", id="marker only"),
    ],
)
async def test_challenge_served_as_a_200_is_detected(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, body: str
) -> None:
    """Bot protection answers 200 with HTML, so the body has to be inspected."""
    aioclient_mock.get(URL, status=200, text=body)

    with pytest.raises(RoverBlockedError):
        await client(hass).async_get_conversations()


@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_cookie_is_an_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """A rejected cookie must reach the user as a reauth prompt, not a retry."""
    aioclient_mock.get(URL, status=status, text="denied")

    with pytest.raises(RoverAuthError):
        await client(hass).async_get_conversations()


async def test_signed_out_200_is_an_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A signed-out session is a 200 carrying `detail`, not a 401."""
    aioclient_mock.get(
        URL,
        status=200,
        json={"detail": "Authentication credentials were not provided."},
    )

    with pytest.raises(RoverAuthError, match="Authentication credentials"):
        await client(hass).async_get_conversations()


@pytest.mark.parametrize(
    ("kwargs", "expected_message"),
    [
        pytest.param({"status": 500, "text": "oops"}, "HTTP 500", id="server error"),
        pytest.param({"status": 429, "text": "slow down"}, "HTTP 429", id="throttled"),
        pytest.param({"text": "not json at all"}, "non-JSON", id="not json"),
        pytest.param({"json": ["a", "list"]}, "JSON object", id="wrong json type"),
    ],
)
async def test_other_failures_are_connection_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    kwargs: dict[str, object],
    expected_message: str,
) -> None:
    """Anything else is transient and safe to retry on the next interval."""
    aioclient_mock.get(URL, **kwargs)

    with pytest.raises(RoverConnectionError, match=expected_message):
        await client(hass).async_get_conversations()


async def test_socket_failure_is_a_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Network exceptions are wrapped rather than escaping as aiohttp errors."""
    aioclient_mock.get(URL, exc=TimeoutError)

    with pytest.raises(RoverConnectionError, match="Could not reach Rover"):
        await client(hass).async_get_conversations()
