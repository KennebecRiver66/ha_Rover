"""Tests for the cookie normaliser and its shape check.

Pure functions, so these are cheap - and they are the part of setup a stranger
meets first, which makes them worth pinning precisely.
"""

from __future__ import annotations

import pytest

from custom_components.rover_client.cookie import (
    cookie_names,
    cookie_problem,
    count_cookies,
    normalise_cookie,
)

PAIR = "csrftoken=fake-csrf-token"
TWO_PAIRS = "__cf_bm=fake-cf-value; csrftoken=fake-csrf-token"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(TWO_PAIRS, TWO_PAIRS, id="already clean"),
        pytest.param(f"  {TWO_PAIRS}  ", TWO_PAIRS, id="surrounding whitespace"),
        pytest.param(f"Cookie: {TWO_PAIRS}", TWO_PAIRS, id="header name attached"),
        pytest.param(f"cookie:{TWO_PAIRS}", TWO_PAIRS, id="lowercase, no space"),
        pytest.param(f"'{TWO_PAIRS}'", TWO_PAIRS, id="document.cookie from console"),
        pytest.param(f'"{TWO_PAIRS}"', TWO_PAIRS, id="double quoted"),
        pytest.param(
            "__cf_bm=fake-cf-value;csrftoken=fake-csrf-token",
            TWO_PAIRS,
            id="no space after separator",
        ),
        pytest.param(f"{TWO_PAIRS};", TWO_PAIRS, id="trailing separator"),
        pytest.param(
            "__cf_bm=fake-cf-value;\n  csrftoken=fake-csrf-token",
            TWO_PAIRS,
            id="wrapped between pairs",
        ),
        pytest.param(
            "__cf_bm=fake-cf-value; csrftoken=fake-csrf\n-token",
            TWO_PAIRS,
            id="wrapped inside a value",
        ),
        pytest.param(
            f"{TWO_PAIRS}; notapair; =novalue",
            TWO_PAIRS,
            id="fragments that are not pairs are dropped",
        ),
        pytest.param("", "", id="empty"),
        pytest.param("   \n ", "", id="whitespace only"),
        pytest.param("no pairs here", "", id="prose"),
    ],
)
def test_normalise_cookie(raw: str, expected: str) -> None:
    """Every paste a user plausibly produces becomes one canonical header."""
    assert normalise_cookie(raw) == expected


def test_normalise_cookie_keeps_spaces_in_a_quoted_value() -> None:
    """A quoted value may legitimately contain a space, so it is left alone."""
    assert normalise_cookie('a="one two"; b=three') == 'a="one two"; b=three'


def test_normalise_cookie_keeps_base64_padding_and_case() -> None:
    """Values pass through untouched apart from whitespace.

    Rover's cookies are opaque - base64 padding, dots and percent-encoding all
    appear - so anything clever here would corrupt a working session.
    """
    raw = "sessionid=YWJjZA==; roverid=a.b%2Fc-D_E"
    assert normalise_cookie(raw) == raw


@pytest.mark.parametrize(
    ("cookie", "expected"),
    [
        pytest.param("", "invalid_cookie_format", id="nothing usable"),
        pytest.param(PAIR, "partial_cookie", id="one cookie from the table"),
        pytest.param(TWO_PAIRS, None, id="a plausible header"),
    ],
)
def test_cookie_problem(cookie: str, expected: str | None) -> None:
    """The shape check separates the two mistakes that used to look identical."""
    assert cookie_problem(normalise_cookie(cookie)) == expected


def test_cookie_problem_never_judges_the_session() -> None:
    """A well-formed header always passes the local check.

    Whether the session behind it is signed in is Rover's answer to give, and
    guessing at it here is what would produce a wrong, confident error message.
    """
    assert cookie_problem(normalise_cookie("a=1; b=2; c=3")) is None


def test_count_and_names_for_diagnostics() -> None:
    """Diagnostics report the shape of the header and never its values."""
    cookie = normalise_cookie(f"Cookie: {TWO_PAIRS}")

    assert count_cookies(cookie) == 2
    assert cookie_names(cookie) == ["__cf_bm", "csrftoken"]
    assert "fake-csrf-token" not in " ".join(cookie_names(cookie))
