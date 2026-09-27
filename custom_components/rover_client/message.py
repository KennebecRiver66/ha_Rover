"""Wording for the door-code reminder.

WHY THIS IS A MODULE AND NOT A TEMPLATE IN THE DOCS
---------------------------------------------------
The message is read by a person who is about to let themselves into a stranger's
house, and it arrives from a home-automation system. A template that produces
"ACCESS CODE: 1234. SERVICE: dog-walking." is the reason people distrust these
messages and ring the doorbell instead. So the phrasing lives in code, gets
several natural variants, and is picked from at random - which also stops a sitter
who walks the dog three times a week from receiving the identical sentence every
time, the other thing that makes a message read as machine-generated.

WHAT IT REFUSES TO DO
---------------------
`requires_house_access` fails CLOSED. An unrecognised service type returns False,
so a slug this integration has never seen produces no code rather than a guess -
the asymmetry is deliberate, because the cost of a missed reminder is a phone call
and the cost of a wrong one is a door code sent to somebody who is keeping the dog
at their own house.

Nothing here logs. The code is a house key.
"""

from __future__ import annotations

import random
from datetime import date, datetime

from homeassistant.util import dt as dt_util

from .const import ACCESS_SERVICE_KEYWORDS, NO_ACCESS_SERVICE_KEYWORDS

# Written out in full rather than assembled from interchangeable openers and
# closers: mixing fragments is how you get "Morning! quick one before your walk
# tomorrow, thanks again for doing this!" - grammatical, and unmistakably a robot.
# Each variant is one person's whole sentence.
#
# `{name}` carries its own leading space so that a missing sitter name leaves
# "Hi!" rather than "Hi !".
TEMPLATES: tuple[str, ...] = (
    (
        "Hi{name}! Just a heads up before {when} - the door code is {code}. "
        "The keypad is on the front door, and it locks itself behind you. "
        "Thanks so much!"
    ),
    (
        "Hey{name}, sending the door code over ahead of {when}: {code}. "
        "Tap that into the keypad and you're in. Thanks again!"
    ),
    (
        "Hi{name} - quick one before {when}. The door code is {code}, on the "
        "keypad by the front door. If it gives you any trouble just message me "
        "here. Thank you!"
    ),
    (
        "Hey{name}! The door code for {when} is {code}. Please give the door a "
        "pull on your way out so it locks behind you, and thanks again for "
        "doing this."
    ),
)

# What to call the service in a sentence. "Your dog-walking" is not English.
SERVICE_PHRASES: tuple[tuple[str, str], ...] = (
    ("walk", "walk"),
    ("drop-in", "drop-in"),
    ("drop_in", "drop-in"),
    ("dropin", "drop-in"),
    ("sitting", "stay"),
)

# Used when the service type is unknown or unrecognised. Deliberately vague: a
# wrong noun ("your walk" for a drop-in) reads worse than a general one.
DEFAULT_SERVICE_PHRASE = "visit"


def requires_house_access(service_type: str | None) -> bool:
    """Return True only if this service is performed at the owner's home.

    Unknown in means False out. See the module docstring for why that asymmetry
    is the point rather than a limitation.
    """
    if not service_type:
        return False

    slug = service_type.strip().lower()
    if any(keyword in slug for keyword in NO_ACCESS_SERVICE_KEYWORDS):
        return False
    return any(keyword in slug for keyword in ACCESS_SERVICE_KEYWORDS)


def service_phrase(service_type: str | None) -> str:
    """Return a noun for the service that can follow the word "your"."""
    if not service_type:
        return DEFAULT_SERVICE_PHRASE

    slug = service_type.strip().lower()
    for keyword, phrase in SERVICE_PHRASES:
        if keyword in slug:
            return phrase
    return DEFAULT_SERVICE_PHRASE


def format_arrival(arrival: datetime | date | None, now: datetime) -> str:
    """Return a clause like "at 3pm today", or "" when the time is unknown.

    `now` is passed in rather than read from the clock so that the wording is
    testable, and so that "today" means today in the user's timezone.
    """
    if arrival is None:
        return ""

    # datetime is a subclass of date, so this order matters.
    if isinstance(arrival, datetime):
        local = dt_util.as_local(arrival)
        return f"at {_clock(local)} {_day(local.date(), now.date())}".strip()

    return _day(arrival, now.date())


def _clock(value: datetime) -> str:
    """Render a time the way somebody would type it: 3pm, 3:30pm, 12:05am."""
    hour = value.hour % 12 or 12
    meridiem = "am" if value.hour < 12 else "pm"
    if value.minute:
        return f"{hour}:{value.minute:02d}{meridiem}"
    return f"{hour}{meridiem}"


def _day(target: date, today: date) -> str:
    """Render a date relative to today, the way somebody would say it."""
    delta = (target - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    # Only inside the coming week, because "on Tuesday" is ambiguous once it
    # could mean a Tuesday nine days away.
    if 2 <= delta <= 6:
        return f"on {target.strftime('%A')}"
    return f"on {target.strftime('%B')} {target.day}"


def compose_message(
    *,
    code: str,
    sitter: str | None = None,
    service_type: str | None = None,
    arrival: datetime | date | None = None,
    now: datetime | None = None,
    extra_note: str | None = None,
    variant: int | None = None,
) -> str:
    """Return one reminder, worded like a message a person would send.

    `variant` selects a template by index for tests and for anyone who prefers a
    fixed wording; left out, it is chosen at random so a weekly sitter does not
    receive the same sentence every time.
    """
    if variant is None:
        template = random.choice(TEMPLATES)
    else:
        template = TEMPLATES[variant % len(TEMPLATES)]

    clause = format_arrival(arrival, now or dt_util.now())
    phrase = service_phrase(service_type)
    when = f"your {phrase} {clause}".strip() if clause else f"your {phrase}"

    name = (sitter or "").strip()
    message = template.format(
        name=f" {name}" if name else "",
        when=when,
        code=code,
    )

    note = (extra_note or "").strip()
    if note:
        message = f"{message} {note}"
    return message
