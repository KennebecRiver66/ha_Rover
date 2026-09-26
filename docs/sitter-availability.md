# Sitter availability — design, and why it isn't built yet

The most useful thing this integration cannot currently answer is "who is free on
the 7th?". The data for it exists, on a **different and better data source** than
everything else here: a sitter's public Rover calendar needs no cookie and does not
sit behind the bot challenge that blocks `/api/v3/stays/<id>/`.

The author's original YAML setup read exactly this and produced, per sitter:

- which roles they offer (boarding / drop-in visits / walking);
- weekly availability preferences (the "usually free on Tuesdays" pattern);
- per-date overrides (the specific days they have blocked out);
- a booking base URL.

This document is the design for porting it. It is **not implemented**, and the last
section says why that is the right call for now rather than laziness.

## Shape: a second coordinator, not an extension of the first

Availability must not be bolted onto `RoverCoordinator`. The two data sources have
nothing in common except the word Rover:

| | Conversations (built) | Availability (this design) |
|---|---|---|
| Auth | Session cookie, expires every few weeks | None |
| Bot challenge | Yes, and it decides what data can exist | No |
| Failure modes | Reauth, blocked, transient | Transient, and "sitter no longer public" |
| Natural interval | 6 hours | 12–24 hours; calendars change far more slowly |
| Reauth flow | Required | Meaningless |

Sharing a coordinator would mean a dead cookie taking availability offline with it,
which would be a straightforward regression: availability does not need the cookie
and should keep working when the cookie dies. So:

```
custom_components/rover_client/
├── coordinator.py               RoverCoordinator          (exists)
├── availability_coordinator.py  AvailabilityCoordinator    (new)
└── api.py                       RoverClient + AvailabilityClient
```

`entry.runtime_data` becomes a small dataclass holding both coordinators rather than
one coordinator. That is a breaking change for nothing else, since `runtime_data` is
internal to this integration.

## Configuration

Sitters have to be named somehow. Options, in order of preference:

1. **Derive them from conversations.** The authenticated payload already carries
   `provider.id` and `provider.first_name` for everyone the account has talked to,
   which is very close to "the sitters I actually use". Needs the mapping from
   `provider.id` to a public profile URL to be verified (see below). If it holds,
   availability needs no configuration at all, which is by far the best outcome.
2. **An options-flow list of profile URLs**, pasted by the user. Always works, but it
   is more setup, and this integration's setup is already the hardest part of it.

Design for 1, fall back to 2 if the mapping does not hold. Either way availability is
opt-in: a checkbox in options, default off, so that existing installs do not silently
start making a second class of request.

## Entities

One sensor per sitter, on its own device grouped under the same service:

```
sensor.rover_availability_<sitter>     state: available | unavailable | unknown
```

State is availability **today**, so it is glanceable. The answerable question lives in
the attributes:

| Attribute | Example |
|---|---|
| `roles` | `["boarding", "drop_in", "walking"]` |
| `weekly` | `{"mon": true, "tue": true, ..., "sun": false}` |
| `overrides` | `{"2026-10-07": false, "2026-10-08": true}` |
| `booking_url` | `https://www.rover.com/...` |

Which makes the original question a template:

```yaml
{{ state_attr('sensor.rover_availability_alex', 'overrides').get('2026-10-07',
   state_attr('sensor.rover_availability_alex', 'weekly')['wed']) }}
```

A `calendar` entity was considered and rejected for a first pass: a calendar implies
events with start and end times, and what this source gives is a recurring weekly
pattern plus date overrides. Rendering that as events means inventing times, and
inventing times is precisely the mistake the conversations half of this integration
refuses to make.

Naming keeps `has_entity_name`, so the IDs stay `sensor.rover_*`.

## Failure handling

- The endpoint is public, so **no reauth, ever**. `RoverAuthError` has no meaning
  here and the client must not raise it.
- A sitter whose profile has gone private or been deleted is a per-sitter failure, not
  a coordinator failure: that sensor goes `unknown`, the others carry on.
- A bot challenge is not expected. If one appears, treat it as transient
  (`UpdateFailed`) rather than a reported state — unlike conversations, nothing here
  is worth showing a dedicated `blocked` state for.
- The interval stays long and gets its own floor. Public does not mean "fine to poll
  every minute".

## Privacy

Sitter first names are other people's personal data, which is why diagnostics today
report counts and service types rather than names. Availability makes this sharper,
because sitter names would become part of entity IDs. So:

- diagnostics report the number of sitters and their roles, never names or URLs;
- the design is opt-in, as above;
- tests and fixtures use invented sitters, exactly as the current suite does.

## What has to be verified before any of this is written

None of the following can be checked from a machine without a browser session and a
clean IP — `https://www.rover.com/` answers `403` to a plain request from here — and
the reconnaissance in [`api.py`](../custom_components/rover_client/api.py) is the
reason this integration is trustworthy about what it can and cannot do. Guessing at an
undocumented payload and shipping the guess would undo that.

1. The public sitter profile URL, and whether `provider.id` from the conversations
   payload maps onto it.
2. The request that returns availability as JSON rather than embedded in HTML. If it
   is only available as HTML, that changes the design substantially and probably means
   parsing markup, which is far more fragile and needs saying out loud in the README.
3. The exact shape of the weekly preferences and the date overrides, including how an
   override that says "available" differs from one that says "unavailable".
4. Whether roles come from the same response or a second one.
5. Whether the response is stable enough to poll unauthenticated without a challenge
   appearing eventually.

The author's original YAML did all of this once. **That YAML, or a redacted capture of
one response per endpoint, is the missing input** — with it, this design becomes a
straightforward port; without it, any implementation would be a plausible-looking
fiction, and the person who eventually finds out would be a stranger whose "who is
free on the 7th?" answer was wrong.
