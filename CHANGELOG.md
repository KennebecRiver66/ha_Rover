# Changelog

All notable changes to this integration are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-26

The "someone other than the author can install this" release. No breaking changes:
entity IDs, the config entry and the cookie you already pasted are all untouched.

### Added

- **Brand images**, shipped inside the integration (`brand/`), so Home Assistant
  shows an icon instead of a generic puzzle piece. Read directly by Home Assistant
  2026.3 and later; older versions still need the images on the brands CDN, and
  `docs/brands-submission.md` has those steps.
- **A test suite**, 83 tests, running the integration inside a real Home Assistant:
  the config and reauth flows, every form error, the parser against realistic and
  malformed payloads, the three failure modes, the session sensor's availability
  rule, and diagnostics redaction. Run in CI on every push.
- **An options flow for the poll interval.** Six hours stays the default; one hour
  is the floor, enforced in the form and again in the coordinator, with the reason
  stated in the UI.
- **A repair issue for a persistent bot challenge.** Four challenges in a row - a
  day at the default interval - now says so on the Repairs page, because being
  blocked is reported as a state rather than a failure and nothing else would tell
  you data had stopped.
- **Setup screenshots and a diagram** of where the `Cookie` header lives, plus a
  redacted example of a valid value, in the README and in the setup form itself.
- Repository furniture: `CONTRIBUTING.md`, issue templates that warn against
  pasting a real cookie, a pull request template, and this changelog.
- `docs/sitter-availability.md`: the design for reading sitters' public calendars
  as a second, unauthenticated coordinator, and what has to be verified first.

### Changed

- **`sensor.rover_session` now reports why a poll failed** instead of holding the
  last value it saw. It used to read `Signed in` throughout an outage, because a
  failed update leaves the previous successful data in place - the diagnostic sensor
  reproducing the exact failure it exists to reveal. `not_signed_in` and `error`
  were already documented and translated states that nothing could produce; now they
  appear when they apply.
- **A pasted cookie is now repaired where it can be.** A leading `Cookie:`, the
  quotes a `document.cookie` value arrives with, and the line wrapping devtools adds
  are all handled, instead of being rejected.
- **The two lookalike setup failures are told apart.** A single `name=value` pair is
  diagnosed locally as "that is one cookie, not the header" without a pointless
  authenticated request to a bot-protected endpoint; a whole header that Rover
  rejects now says the browser it came from has probably signed out.
- Diagnostics report the cookie's shape - how many pairs, and their names - which is
  what answers the commonest setup question. Values are still redacted, and sitters
  are still counted rather than named.
- `translations/en.json` is generated from `strings.json` by
  `scripts/sync_translations.py`, with a CI check, rather than being a second copy
  of every sentence maintained by hand.
- The README documents the one-Rover-account-per-Home-Assistant limitation, which
  was previously unstated.
- CI no longer ignores the HACS brands check.

## [0.1.0] - 2026-09-26

First release: the working YAML setup extracted into a HACS-installable
integration.

### Added

- `sensor.rover_session`, `sensor.rover_latest_service_type` (with a sitter →
  service-type map in its attributes) and `sensor.rover_conversations`, on one
  service device.
- Cookie-based setup and a reauth flow, because a browser session cookie expires
  every few weeks and re-pasting one is normal operation.
- A six-hour poll of `/api/v3/conversations/`, deliberately slow: the endpoint is
  behind bot protection.
- Three distinguished failure modes - rejected cookie, bot challenge, network error
  - each mapped to the Home Assistant reaction that fits it.
- Diagnostics with the cookie redacted and sitters counted rather than named.

[0.2.0]: https://github.com/KennebecRiver66/HARoverClient/releases/tag/v0.2.0
[0.1.0]: https://github.com/KennebecRiver66/HARoverClient/releases/tag/v0.1.0
