Reads your Rover account so Home Assistant automations can react to dog-care bookings: which sitter, and what kind of service.

Needs a `Cookie:` header copied from a browser where you are signed in to Rover — Rover has no public API and its login is behind a bot check. That copy-and-paste is the hardest part of setup, so the [README](https://github.com/KennebecRiver66/HARoverClient#setting-it-up) has a diagram of where to find it and a redacted example of what a valid value looks like. The cookie expires every few weeks and Home Assistant will prompt you for a fresh one, keeping your entities and history.

**Booking times are not available** through this route, and only one Rover account is supported per Home Assistant. See the README for why, and for the other limitations.
