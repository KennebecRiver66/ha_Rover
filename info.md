Reads your Rover account so Home Assistant automations can react to dog-care bookings: which sitter, and what kind of service.

Needs a `Cookie:` header copied from a browser where you are signed in to Rover — Rover has no public API and its login is behind a bot check. That copy-and-paste is the hardest part of setup, so the [README](https://github.com/KennebecRiver66/HARoverClient#setting-it-up) has a diagram of where to find it and a redacted example of what a valid value looks like. The cookie expires every few weeks and Home Assistant will prompt you for a fresh one, keeping your entities and history.

If a sitter has to get into your house for a walk or a drop-in, there is a service that writes the door-code reminder for you in the wording of a person, plus a blueprint that sends it a set time before they are due. It hands the text back rather than posting into Rover, which cannot be written to from Home Assistant — see [the walkthrough](https://github.com/KennebecRiver66/HARoverClient/blob/main/docs/access-code-reminders.md).

**Booking times are not available** through this route, and only one Rover account is supported per Home Assistant. See the README for why, and for the other limitations.
