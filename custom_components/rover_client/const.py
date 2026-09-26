"""Constants for the Rover Client integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "rover_client"

CONF_COOKIE: Final = "cookie"

BASE_URL: Final = "https://www.rover.com"
CONVERSATIONS_PATH: Final = "/api/v3/conversations/"

# Rover's own site is fronted by a bot-detection layer that scores the client
# fingerprint. A stale User-Agent is one of the cheapest ways to look automated,
# so this is kept in ONE place and bumped deliberately rather than copied around.
USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)

# Six hours. This is NOT a placeholder to be tuned down casually: the endpoint
# sits behind bot protection, and a tight poll against an authenticated session
# is exactly the pattern that earns a block. Conversations change on the order of
# days, so six hours costs nothing real.
DEFAULT_SCAN_INTERVAL: Final = timedelta(hours=6)

# How many conversations to read service types from. The API returns newest
# first; ten covers "we booked several sitters at once" without walking history.
CONVERSATION_SCAN_DEPTH: Final = 10

SESSION_SIGNED_IN: Final = "signed_in"
SESSION_NOT_SIGNED_IN: Final = "not_signed_in"
SESSION_BLOCKED: Final = "blocked"
SESSION_ERROR: Final = "error"

# Fewer pairs than this and the paste is a single cookie from the devtools cookie
# table rather than a whole Cookie header. See cookie.py for why the check counts
# pairs instead of looking for particular cookie names.
MIN_COOKIE_PAIRS: Final = 2

# Repair issue raised when the saved session stops being accepted. A reauth card
# in Settings is correct but quiet, and this failure is a routine one - the cookie
# expires every few weeks - so it also belongs somewhere the user cannot miss it.
ISSUE_SESSION_EXPIRED: Final = "session_expired"
