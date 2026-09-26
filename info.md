Reads your Rover account so Home Assistant automations can react to dog-care bookings: which sitter, and what kind of service.

Needs a `Cookie:` header copied from a browser where you are signed in to Rover — Rover has no public API and its login is behind a bot check. The cookie expires every few weeks and Home Assistant will prompt you for a fresh one.

**Booking times are not available** through this route. See the README for why, and for the other limitations.
