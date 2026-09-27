"""Tests for the door-code reminder wording.

Nothing here is a real code, a real sitter or a real house.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from custom_components.rover_client.message import (
    TEMPLATES,
    compose_message,
    format_arrival,
    requires_house_access,
    service_phrase,
)
from homeassistant.util import dt as dt_util

FAKE_CODE = "135790"
FAKE_SITTER = "Testsitter"

# A Tuesday, so the weekday wording is predictable. Naive on purpose: the
# composer reads every arrival in the user's own timezone, so writing these as
# wall-clock times is both what a user means and independent of where the tests
# happen to run.
NOW = datetime(2026, 9, 29, 9, 0)


@pytest.mark.parametrize(
    "service_type",
    [
        "dog-walking",
        "DOG-WALKING",
        " dog-walking ",
        "drop-in-visit",
        "drop-in-visits",
        "drop_in_visit",
        "house-sitting",
    ],
)
def test_services_at_your_home_need_access(service_type: str) -> None:
    """A walk, a drop-in or house-sitting all need somebody in the house."""
    assert requires_house_access(service_type) is True


@pytest.mark.parametrize(
    "service_type",
    [
        "overnight-boarding",
        "doggy-day-care",
        "daycare",
        "grooming",
    ],
)
def test_services_at_the_sitters_home_do_not(service_type: str) -> None:
    """Boarding and day care happen at the sitter's house, so no code goes out."""
    assert requires_house_access(service_type) is False


@pytest.mark.parametrize("service_type", [None, "", "something-rover-invented"])
def test_unknown_service_fails_closed(service_type: str | None) -> None:
    """An unrecognised service type must not produce a door code.

    The whole point of the classifier: guessing wrong in this direction sends a
    house key to somebody who is keeping the dog at their own place.
    """
    assert requires_house_access(service_type) is False


def test_a_service_that_reads_as_both_is_treated_as_boarding() -> None:
    """Deny wins over allow, so an ambiguous slug cannot open the door."""
    assert requires_house_access("boarding-and-walking") is False


@pytest.mark.parametrize(
    ("service_type", "expected"),
    [
        ("dog-walking", "walk"),
        ("drop-in-visit", "drop-in"),
        ("house-sitting", "stay"),
        ("overnight-boarding", "visit"),
        (None, "visit"),
    ],
)
def test_service_phrase_is_a_noun_you_can_say(
    service_type: str | None, expected: str
) -> None:
    """The message says "your walk", never "your dog-walking"."""
    assert service_phrase(service_type) == expected


@pytest.mark.parametrize(
    ("arrival", "expected"),
    [
        (datetime(2026, 9, 29, 15, 0), "at 3pm today"),
        (datetime(2026, 9, 30, 15, 30), "at 3:30pm tomorrow"),
        (datetime(2026, 10, 1, 8, 0), "at 8am on Thursday"),
        (datetime(2026, 10, 20, 12, 0), "at 12pm on October 20"),
        (datetime(2026, 9, 29, 0, 5), "at 12:05am today"),
        # An all-day calendar event, which is how "sometime Tuesday" gets recorded.
        (date(2026, 9, 30), "tomorrow"),
        (date(2026, 10, 1), "on Thursday"),
        (None, ""),
    ],
)
def test_arrival_reads_like_a_person_wrote_it(
    arrival: datetime | date | None, expected: str
) -> None:
    """Relative where a person would be relative, absolute once that gets vague."""
    assert format_arrival(arrival, NOW) == expected


def test_an_arrival_with_a_timezone_is_shown_in_the_local_one() -> None:
    """A calendar event carries an offset; the sitter reads a wall clock.

    Stated as a test because the alternative is telling somebody to arrive at
    10pm for a 3pm walk, which is the kind of bug that only shows up in summer.
    """
    arrival = datetime(2026, 9, 29, 22, 30, tzinfo=dt_util.UTC)
    local = dt_util.as_local(arrival)
    expected_hour = local.hour % 12 or 12
    expected_meridiem = "am" if local.hour < 12 else "pm"

    clause = format_arrival(arrival, local)

    assert clause == f"at {expected_hour}:30{expected_meridiem} today"


@pytest.mark.parametrize("variant", range(len(TEMPLATES)))
def test_every_variant_is_a_message_you_could_send(variant: int) -> None:
    """Each wording must carry the code and read as a finished sentence."""
    message = compose_message(
        code=FAKE_CODE,
        sitter=FAKE_SITTER,
        service_type="dog-walking",
        arrival=datetime(2026, 9, 29, 15, 0),
        now=NOW,
        variant=variant,
    )

    assert FAKE_CODE in message
    assert FAKE_SITTER in message
    assert "your walk at 3pm today" in message
    assert message[0].isupper()
    assert message.endswith(("!", "."))
    # The join points are where fragment-assembly goes wrong.
    assert "  " not in message
    assert " ," not in message
    assert " !" not in message


@pytest.mark.parametrize("variant", range(len(TEMPLATES)))
def test_a_missing_sitter_name_does_not_leave_a_hole(variant: int) -> None:
    """Without a name the greeting has to still be a greeting."""
    message = compose_message(code=FAKE_CODE, now=NOW, variant=variant)

    assert FAKE_CODE in message
    assert "Hi !" not in message
    assert "Hi ," not in message
    assert "  " not in message
    assert "your visit" in message


def test_variants_are_not_all_the_same() -> None:
    """Variety is the feature: a weekly sitter should not get one stock sentence."""
    rendered = {
        compose_message(code=FAKE_CODE, now=NOW, variant=index)
        for index in range(len(TEMPLATES))
    }
    assert len(rendered) == len(TEMPLATES)


def test_random_wording_is_always_one_of_the_variants() -> None:
    """Called without a variant it picks one, rather than inventing wording."""
    expected = {
        compose_message(code=FAKE_CODE, now=NOW, variant=index)
        for index in range(len(TEMPLATES))
    }
    for _ in range(25):
        assert compose_message(code=FAKE_CODE, now=NOW) in expected


def test_extra_note_is_appended_as_written() -> None:
    """The user's own sentence goes on the end untouched."""
    message = compose_message(
        code=FAKE_CODE,
        now=NOW,
        extra_note="  The leash is on the hook by the back door.  ",
        variant=0,
    )

    assert message.endswith("The leash is on the hook by the back door.")
    assert "  " not in message


def test_an_empty_note_adds_nothing() -> None:
    """An unset blueprint input arrives as an empty string, not as None."""
    assert compose_message(
        code=FAKE_CODE, now=NOW, extra_note="   ", variant=0
    ) == compose_message(code=FAKE_CODE, now=NOW, variant=0)


def test_arrival_defaults_to_the_current_clock() -> None:
    """Omitting `now` is allowed, and still produces a sensible relative day."""
    message = compose_message(
        code=FAKE_CODE,
        arrival=dt_util.now() + timedelta(hours=1),
        variant=0,
    )
    assert "today" in message or "tomorrow" in message


def test_variant_index_wraps() -> None:
    """An out-of-range variant picks a real template rather than raising."""
    assert compose_message(code=FAKE_CODE, now=NOW, variant=99) in {
        compose_message(code=FAKE_CODE, now=NOW, variant=index)
        for index in range(len(TEMPLATES))
    }
