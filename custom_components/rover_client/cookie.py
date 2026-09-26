"""Repairing and sanity-checking a pasted Cookie header.

WHY THIS MODULE EXISTS
----------------------
Copying a `Cookie:` header out of devtools is by far the hardest step of setup,
and the step most installs fail on. Two mistakes account for almost all of it:

  1. Copying one row out of the Application -> Cookies table, which gives a
     single `name=value` pair rather than the whole header.
  2. Copying the header with its name attached (`Cookie: a=1; b=2`), or with the
     line wrapping devtools adds, which puts whitespace inside a cookie value.

The second kind is repairable without asking the user anything, so it is repaired
here. The first kind is not repairable, but it IS recognisable, and telling
someone "you pasted a single cookie" is a different and far more useful message
than "Rover rejected that cookie" - which is what a partial header would
otherwise produce after a pointless round trip to Rover.

A `document.cookie` value from the browser console is already in header format,
so it is accepted by the same path; the only extra handling it needs is stripping
the quotes the console prints around it.
"""

from __future__ import annotations

from .const import MIN_COOKIE_PAIRS

_HEADER_NAME_PREFIX = "cookie:"
_QUOTES = ("'", '"')


def normalise_cookie(raw: str) -> str:
    """Return a pasted cookie as a canonical `name=value; name=value` header.

    Anything that is not a `name=value` pair is dropped rather than passed
    through, so that a paste of prose or of a bare cookie name normalises to the
    empty string and is reported as a format problem instead of being sent to
    Rover as a header it will simply reject.
    """
    text = raw.strip()

    if len(text) >= 2 and text[0] in _QUOTES and text[-1] == text[0]:
        text = text[1:-1].strip()

    if text.lower().startswith(_HEADER_NAME_PREFIX):
        text = text[len(_HEADER_NAME_PREFIX) :].strip()

    pairs = [_normalise_pair(part) for part in text.split(";")]
    return "; ".join(pair for pair in pairs if pair)


def _normalise_pair(part: str) -> str:
    """Return one `name=value` pair, or an empty string if it is not one."""
    pair = part.strip()
    if "=" not in pair:
        return ""

    name, _, value = pair.partition("=")
    name = "".join(name.split())
    value = value.strip()

    # Whitespace inside an unquoted cookie value is never valid, so any that is
    # present came from devtools wrapping a long header across lines and can be
    # removed. A quoted value is left alone, because there a space is real.
    if not (len(value) >= 2 and value[0] == '"' and value[-1] == '"'):
        value = "".join(value.split())

    if not name:
        return ""
    return f"{name}={value}"


def count_cookies(cookie: str) -> int:
    """Return how many `name=value` pairs a normalised cookie header holds."""
    return len([part for part in cookie.split(";") if part.strip()])


def cookie_names(cookie: str) -> list[str]:
    """Return the names in a normalised header, for diagnostics.

    Names only. The values are the credential; see diagnostics.py.
    """
    return sorted(
        part.partition("=")[0].strip()
        for part in cookie.split(";")
        if part.strip()
    )


def cookie_problem(cookie: str) -> str | None:
    """Return a config-flow error key if the paste cannot be a session header.

    Deliberately shallow: it checks shape, never whether the session is any good.
    Only Rover can answer that, and a valid-looking header from a signed-out
    browser has to come back as `invalid_auth` from the API call. The point of
    this check is that the two failures stop being reported as the same thing.
    """
    if not cookie:
        return "invalid_cookie_format"

    # A signed-in rover.com session carries a handful of cookies, so one pair is
    # a paste from the cookie table rather than a header. The threshold is low on
    # purpose: guessing at required cookie NAMES would hard-code an undocumented
    # detail of someone else's site, and it would fail closed the day they
    # rename one.
    if count_cookies(cookie) < MIN_COOKIE_PAIRS:
        return "partial_cookie"

    return None
