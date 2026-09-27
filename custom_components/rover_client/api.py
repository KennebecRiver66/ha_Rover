"""Thin async client for the Rover web API.

WHY A COOKIE AND NOT A PASSWORD
-------------------------------
Rover has no public API and no OAuth. Its sign-in endpoints sit behind a
bot-detection challenge, so a scripted username/password login cannot complete -
it is answered with an interstitial page, not a token. Reusing a session cookie
from an already-signed-in browser is the only approach that works today.

WHAT IS AND IS NOT REACHABLE WITH THAT COOKIE
---------------------------------------------
Verified against the live site:

  GET /api/v3/conversations/     works. Returns JSON. NOT behind the challenge.
  GET /api/v3/stays/<id>/        blocked by the bot challenge.
  GET /account/stays/<id>/       blocked by the bot challenge.

That split is the single most important fact about this integration, because it
decides what data can exist. Conversations carry the sitter and the service type.
They do NOT carry booking times: `stay_meta` holds only locations plus an
`itinerary_url`, and that URL returns an HTML document rather than JSON. `request`
is null and `events` is the chat thread. So drop-off and pick-up times are not
obtainable through this route at all - do not add a sensor promising them.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import BASE_URL, CONVERSATIONS_PATH, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class RoverError(Exception):
    """Base error for this client."""


class RoverAuthError(RoverError):
    """The session cookie is missing, expired or rejected.

    Callers must translate this into ConfigEntryAuthFailed so Home Assistant
    starts a reauth flow. It must never be retried silently - a dead cookie does
    not recover on its own, and retrying it is what gets an IP flagged.
    """


class RoverBlockedError(RoverError):
    """Bot protection answered with a challenge page instead of our data.

    Distinct from RoverAuthError on purpose: the cookie may be perfectly valid.
    Backing off is the correct response; asking the user for a new cookie is not.
    """


class RoverConnectionError(RoverError):
    """Network-level failure. Transient, safe to retry on the next interval."""


class RoverClient:
    """Reads the Rover web API using a browser session cookie."""

    def __init__(self, session: aiohttp.ClientSession, cookie: str) -> None:
        """Store the shared HA session and the cookie header value."""
        self._session = session
        self._cookie = cookie

    @property
    def _headers(self) -> dict[str, str]:
        """Headers for every request.

        Sent on ALL requests, not just some: a request that omits half of them is
        a different, more obviously automated fingerprint than one that sends the
        full set.
        """
        return {
            "Cookie": self._cookie,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-US",
            "Referer": f"{BASE_URL}/members/",
        }

    async def async_get_conversations(self) -> dict[str, Any]:
        """Return the conversations payload, or raise a typed error.

        The three failure modes are deliberately told apart here rather than at
        the call site, because they need opposite handling: a challenge means back
        off, a rejected cookie means ask the user, a socket error means try again.
        """
        url = f"{BASE_URL}{CONVERSATIONS_PATH}"
        try:
            async with self._session.get(
                url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                text = await response.text()

                # The challenge page is served with a 200 and an HTML body, so the
                # status code alone cannot detect it. Check the body first.
                if "Just a moment" in text or "cf-browser-verification" in text:
                    raise RoverBlockedError(
                        "Rover returned a bot-protection challenge instead of JSON"
                    )

                if response.status in (401, 403):
                    raise RoverAuthError(
                        f"Rover rejected the session cookie (HTTP {response.status})"
                    )

                if response.status != 200:
                    raise RoverConnectionError(
                        f"Rover returned HTTP {response.status}"
                    )

                try:
                    data = await response.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise RoverConnectionError(
                        "Rover returned a non-JSON body"
                    ) from err

                if not isinstance(data, dict):
                    raise RoverConnectionError(
                        f"Expected a JSON object, got {type(data).__name__}"
                    )

                # Signed-out responses are a 200 carrying {"detail": "..."} rather
                # than a 401, which is why this check cannot live with the status
                # codes above.
                if "detail" in data:
                    raise RoverAuthError(str(data["detail"]))

                return data

        except (aiohttp.ClientError, TimeoutError) as err:
            raise RoverConnectionError(f"Could not reach Rover: {err}") from err
