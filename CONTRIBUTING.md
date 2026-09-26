# Contributing

Issues and pull requests are welcome. This is a small integration reading an
undocumented API, so the most valuable contributions are usually evidence: a
redacted payload that the parser mishandles, or a step where setup went wrong.

## Never paste these

> [!CAUTION]
> A Rover `Cookie:` value is a **full-access credential** for the account. Anyone
> who has it can read messages, see addresses and book services. It cannot be
> scoped and it cannot be revoked other than by signing out everywhere.

So, in issues, pull requests, tests, fixtures and commit messages:

- **no real `Cookie:` values**, not even partially — the first few characters of a
  session cookie are still part of a session cookie;
- **no unredacted diagnostics**; download them, open them, and check;
- **no real sitter names, phone numbers, addresses or profile URLs** — those are
  someone else's personal data, and they did not sign up for a bug report;
- **no real account usernames or email addresses.**

Use obviously fake values instead. The test suite's own fixtures are the model:
`Testsitter`, `csrftoken=fake-csrf-token`. If a value looks like it might be real,
it fails review.

## Getting set up

Python 3.14, because that is what the pinned Home Assistant needs.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
python -m pytest
ruff check .
```

`requirements_test.txt` pins `pytest-homeassistant-custom-component`, which pins the
Home Assistant version the tests run against. Bumping it is a deliberate change with
its own commit: a new Home Assistant can change flow helpers and fixtures, and that
should show up as a red run to read rather than as an unrelated PR failing.

Note the two Home Assistant versions in play. `hacs.json` declares a **minimum** of
2025.2.0, which is the oldest release whose APIs this code sticks to; the tests run
against the **current** release. Anything newer than the floor - a helper, a flow
method, a keyword argument - means raising the floor in the same pull request, and
saying so in the changelog. The one deliberate exception is the `brand/` images,
which older versions simply ignore.

## What CI checks

Every push and pull request runs four jobs, all of which must pass:

| Job | What it means |
|---|---|
| `hassfest` | Home Assistant's own manifest, strings and icon validation |
| `HACS validation` | Installable as a HACS custom repository, brand images included |
| `Ruff` | Lint and import order, configured in `pyproject.toml` |
| `Tests` | The suite, plus a check that `translations/en.json` is in sync |

## House rules that are easy to trip over

**`strings.json` is the source of UI text.** `translations/en.json` is generated:

```bash
python3 scripts/sync_translations.py
```

CI fails if you edit one and not the other. Other languages are hand-written and
are only checked for being valid JSON.

**Bump `manifest.json` version** on every user-visible change, and add a
`CHANGELOG.md` entry. HACS shows the version, and an unchanged version number
across two releases is confusing to debug.

**Don't re-add `# noqa: BLE001`** to the blind `except Exception` in
`config_flow.py`. Ruff already allows it there because the exception is logged with
`logger.exception`, so the suppression would be flagged as unused.

**Brand images are generated**, not hand-drawn:

```bash
pip install pillow
python3 scripts/make_brand_assets.py   # custom_components/rover_client/brand/
python3 scripts/make_docs_images.py    # docs/images/cookie-header.png
```

Edit the script, re-run, commit the output. Retouching the PNGs by hand works until
the next run silently undoes it. See [docs/brands-submission.md](docs/brands-submission.md).

## Decisions that are load-bearing

Please read the module docstring in
[`api.py`](custom_components/rover_client/api.py) before proposing a design change.
It records the reconnaissance the whole integration is built on, and it rules out
several changes that look obviously correct from the outside:

- **Cookie auth is not laziness.** Rover has no public API, and its sign-in
  endpoints sit behind a bot challenge that a scripted username/password login
  cannot complete. A username/password flow would not work; please don't add one.
- **Booking times are unobtainable this way.** `/api/v3/conversations/` has no
  dates or times, `stay_meta` has only locations and an HTML `itinerary_url`, and
  the endpoints that do have times are behind the challenge. A "next booking"
  sensor cannot be built from this data source. Times would have to come from
  Rover's confirmation email.
- **The slow poll is deliberate.** A tight poll against an authenticated,
  bot-protected endpoint is how an IP gets flagged. One hour is the hard floor.
- **The three failure modes are told apart on purpose.** A rejected cookie asks the
  user (`ConfigEntryAuthFailed`), a challenge reports a state without marking
  entities unavailable, and a socket error retries (`UpdateFailed`). Collapsing
  them recreates the bug this design avoids: entities frozen at stale values with
  nothing to explain why.
- **`sensor.rover_session` stays available when the others don't.** It is the
  diagnostic sensor. See its `available` property.
- **Diagnostics redact the cookie and report sitter counts rather than names.**
  Keep that property when extending them.
- **Read-only.** Writes would be a separate, explicitly gated concern, and they
  would hit the same bot protection.

## Tests

New behaviour needs a test. The suite runs the integration inside a real Home
Assistant, so prefer asserting behaviour a user could notice — an entity state, a
form error, a repair issue — over asserting that a function was called.

Worth covering more than anything else:

- the parser, against realistic and malformed payloads (it must never raise);
- the config and reauth flows, including that reauth updates the entry **in place**
  so entity IDs survive;
- anything that touches redaction.
