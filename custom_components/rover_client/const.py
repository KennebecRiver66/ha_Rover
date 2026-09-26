"""Constants for the Rover Client integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "rover_client"

CONF_COOKIE: Final = "cookie"
CONF_SCAN_INTERVAL_HOURS: Final = "scan_interval_hours"

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
DEFAULT_SCAN_INTERVAL_HOURS: Final = 6
DEFAULT_SCAN_INTERVAL: Final = timedelta(hours=DEFAULT_SCAN_INTERVAL_HOURS)

# The options flow lets the interval be changed but not removed as a protection:
# one hour is the floor because the reason for polling slowly is Rover's bot
# detection, which no amount of user preference makes safer. A week is the
# ceiling simply so that a fat-fingered entry cannot silently stop updates.
MIN_SCAN_INTERVAL_HOURS: Final = 1
MAX_SCAN_INTERVAL_HOURS: Final = 168

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

# Repair issue for a bot challenge that will not go away.
#
# NOT for an expired cookie: Home Assistant raises its own repair whenever a
# ConfigEntryAuthFailed starts a reauth flow (config_entries.py, and it has done so
# since well before the 2025.2 floor this integration declares), and that card
# opens the reauth dialog directly. A second card saying the same thing in worse
# words is clutter, so there isn't one.
#
# A challenge is the opposite case: nothing is raised, on purpose, because the
# cookie is probably fine and the next poll is hours away. That leaves the one
# outcome this integration exists to prevent - data quietly stopping with nothing
# to explain it - so a run of consecutive challenges gets a repair of its own.
ISSUE_BLOCKED: Final = "blocked_repeatedly"

# Four polls in a row, which is a day at the default interval. One challenge is
# routine and clears itself; four is Rover having decided something about this IP,
# and worth telling a human about.
BLOCKED_POLLS_BEFORE_REPAIR: Final = 4
