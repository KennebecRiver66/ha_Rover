# Rover Client for Home Assistant

A Home Assistant integration that reads your [Rover](https://www.rover.com) account — which sitter you booked and what kind of service it is — so automations can react to dog-care bookings.

> **Status: 0.1.0, early.** The core read path works and is in daily use, but this is a young integration extracted from a working YAML setup. Read [Limitations](#limitations) before installing — some of them are properties of Rover, not bugs that can be fixed here.

## What it gives you

| Entity | Example | What it's for |
|---|---|---|
| `sensor.rover_session` | `Signed in` | Whether the saved session still works. The one sensor that stays readable when the others don't. |
| `sensor.rover_latest_service_type` | `overnight-boarding` | The service type of the newest booking. Its attributes carry a sitter → service-type map. |
| `sensor.rover_conversations` | `14` | How many conversations the account has. A cheap liveness signal. |

The per-sitter map on `sensor.rover_latest_service_type` is the useful part when you book several sitters at once:

```yaml
# Which service did we book with Alex?
{{ state_attr('sensor.rover_latest_service_type', 'Alex') }}   # overnight-boarding
```

## Installation

### HACS (custom repository)

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/KennebecRiver66/HARoverClient`, category **Integration**
3. Install **Rover Client**, then restart Home Assistant
4. **Settings → Devices & services → Add integration → Rover Client**

### Manual

Copy `custom_components/rover_client` into your `config/custom_components/` directory and restart.

## Setting it up

Rover has no public API, and its sign-in endpoints sit behind a bot challenge — a scripted username/password login cannot complete. So this integration reuses a session from a browser where you're already signed in.

1. Sign in at rover.com.
2. Open developer tools (F12) → **Network**.
3. Reload, then click any request to `rover.com`.
4. Under **Request Headers**, copy the entire value of `Cookie:`.
5. Paste it into the integration's setup form.

The cookie lives in Home Assistant's config entry — not in your YAML — and is redacted from diagnostics. **It expires after a few weeks.** When it does, Home Assistant raises a reauth prompt asking for a fresh one; your entities, history and automations are preserved.

## Limitations

These are the honest edges. Most are Rover's, not this integration's.

**Booking times are not available.** This is the big one. `/api/v3/conversations/` returns the sitter and the service type but no dates or times. `stay_meta` holds only locations and an `itinerary_url`, and that URL returns an HTML document rather than JSON. The endpoints that *would* have times — `/api/v3/stays/<id>/` and `/account/stays/<id>/` — are behind the bot challenge and unreachable with a session cookie. If you need drop-off and pick-up times, they have to come from the Rover confirmation **email**, not from here.

**Cookie auth, with all that implies.** No OAuth, no API key, no refresh. The session expires and you re-paste. A cookie is a full-access credential for your Rover account, so treat Home Assistant backups as secrets.

**Polling is deliberately slow — six hours.** The endpoint is behind bot protection, and hammering it with an authenticated session is how an IP gets flagged. Conversations change on the order of days. Don't lower this without a reason.

**Bot challenges happen.** When Rover answers with a challenge instead of JSON, `sensor.rover_session` reports `Blocked` and the other sensors go unavailable. It usually clears on its own; there's nothing to do.

**Read-only.** It cannot book, message, or cancel anything.

## Roadmap

- Sitter availability from sitters' public Rover calendars (no auth needed — a separate, unblocked route)
- A `binary_sensor` for "a booking is active right now"
- Tests, and a `strict-typing` clean bill of health
- Options flow for the poll interval

## Contributing

Issues and PRs welcome. Please never paste a real `Cookie:` value, sitter names, or unredacted diagnostics into an issue.

## Licence

MIT — see [LICENSE](LICENSE).

*Not affiliated with, endorsed by, or supported by Rover.com. It reads your own account on your behalf using your own session, and can break at any time if Rover changes its site.*
