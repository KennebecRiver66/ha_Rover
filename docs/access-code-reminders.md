# Sending a sitter the door code

A walk or a drop-in means somebody letting themselves into your house while you
are out. If you have a keypad lock, the part worth automating is remembering to
send the code — and sending it in words a person would actually use.

This is what the reminder looks like:

```
Hi Testsitter - quick one before your walk at 3pm today. The door code is 135790,
on the keypad by the front door. If it gives you any trouble just message me here.
Thank you!
```

There are four variants and one is picked at random each time, so a sitter who
walks the dog three times a week does not receive the identical sentence every
time. That is a small thing that makes the difference between a message that
reads as a note from you and one that reads as output.

## What does what, and why it is split up

| Piece | Job |
|---|---|
| `binary_sensor.rover_house_access_needed` | Is the newest booking one that happens at *your* house? |
| `rover_client.compose_access_message` | Writes the message and hands it back. Sends nothing. |
| The included blueprint | Decides *when*, checks the guard, and passes the text to whatever you use to send messages. |

Three pieces rather than one setting, because two of the three things you would
want a single setting to do cannot be done from inside this integration:

**It cannot post into the Rover chat.** Rover has no public API. This integration
works by reusing a browser session against `/api/v3/conversations/`, which happens
to be the one endpoint that is not behind Rover's bot-detection challenge. Posting
a message is a different, protected endpoint, and the integration is read-only on
purpose — see [the README](../README.md#limitations). So the message comes back to
you and you choose the pipe.

**It cannot know when the sitter is due.** The conversations endpoint carries the
sitter and the service type and no times at all. The times exist in Rover's
confirmation email and nowhere this integration can reach. So the schedule comes
from a calendar you keep.

Both of those are properties of Rover rather than missing work, which is why the
setup below has a step about a calendar in it.

## Setting it up

### 1. A calendar of visits

Any calendar entity works. The simplest is Home Assistant's built-in
[Local Calendar](https://www.home-assistant.io/integrations/local_calendar/):

1. **Settings → Devices & services → Add integration → Local Calendar**
2. Name it something like `Rover visits`.
3. When you confirm a booking, add the visit to it, using the time from Rover's
   confirmation email.

The event **start** is treated as the sitter's arrival time. Recurring events work
and are worth using for a standing weekly walk. An all-day event works too, and
produces a message that says "your walk tomorrow" rather than inventing a time.

### 2. Somewhere to keep the code

The reminder reads the code from an entity, not from a number typed into the
automation, so that rotating the code does not mean editing the automation.

**If Home Assistant can manage your lock's codes**, point the blueprint at the
relevant `text` entity and you are done. Be aware that the official
[August](https://www.home-assistant.io/integrations/august/) and Yale integrations
**cannot** do this — they give you lock, unlock and battery, but no keypad code
management. Third-party options exist; they are outside the scope of this
integration and you should read them yourself before trusting one with your locks.

**Otherwise**, keep a helper in step with the code you set in the August or Yale
app by hand:

1. **Settings → Devices & services → Helpers → Create helper → Text**
2. Name it `Rover door code`, giving `input_text.rover_door_code`.
3. Put the current guest code in it. Update it whenever you rotate the code.

A dedicated guest code that is not your own everyday code is the right thing to
use here, whichever route you take.

### 3. Import the blueprint

**Settings → Automations & scenes → Blueprints → Import blueprint**, and paste:

```
https://github.com/KennebecRiver66/HARoverClient/blob/main/blueprints/automation/rover_client/access_code_reminder.yaml
```

Then create an automation from it and fill in:

| Input | What to put |
|---|---|
| **Visit calendar** | The calendar from step 1. |
| **How far ahead to send it** | 15 minutes to a day before. An hour is a good default: long enough to be read before the sitter leaves, short enough that the code is not sitting in a notification all day. |
| **Door code** | The entity from step 2. |
| **Anything to add** | Optional sentence of your own, appended as written. Templates work. |
| **House access sensor** | Leave as `binary_sensor.rover_house_access_needed`. |
| **Send the message** | Any action. `{{ message }}` holds the finished text. |

For **Send the message**, sending it to yourself is the recommended default:

```yaml
action: notify.mobile_app_your_phone
data:
  title: Door code for the sitter
  message: "{{ message }}"
```

You then paste it into the Rover app, which takes five seconds and keeps the
sitter's phone number out of Home Assistant entirely. If you would rather it went
straight to the sitter, any SMS notifier works the same way — that is your call to
make, and it is the reason this is an input rather than a decision baked in here.

### Turning it off

It is an ordinary automation, so the toggle on its card is the off switch, and
the trace on it shows exactly what was sent and when. Nothing about the feature
lives in the integration's own options, which is deliberate: there is no second
place to check.

## Doing it without the blueprint

The service is the useful part; the blueprint is just wiring. By hand:

```yaml
automation:
  - alias: Door code before a Rover visit
    triggers:
      - trigger: calendar
        entity_id: calendar.rover_visits
        event: start
        offset: "-01:00:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.rover_house_access_needed
        state: "on"
    actions:
      - action: rover_client.compose_access_message
        data:
          code: "{{ states('input_text.rover_door_code') }}"
          arrival: "{{ trigger.calendar_event.start }}"
        response_variable: composed
      - action: notify.mobile_app_your_phone
        data:
          title: Door code for the sitter
          message: "{{ composed.message }}"
```

The service returns:

| Key | |
|---|---|
| `message` | The finished text. |
| `sitter` | Who it greets — the sitter on the newest booking unless you passed one. |
| `service_type` | The service it was written for. |
| `requires_house_access` | Whether that service needs somebody inside your house. |

Every field is optional except `code`. `sitter` and `service_type` default to the
newest booking, and a missing sitter name just leaves the greeting as "Hi!" rather
than breaking the sentence. Omitting `arrival` produces "before your walk" with no
time in it.

## Why an unknown service sends nothing

`requires_house_access` answers **no** for any service type it does not recognise.

Rover's service-type slugs come from an undocumented API. Two are confirmed
against the live site — `dog-walking` and `drop-in-visit` — and the classifier
matches on substrings so that a rename to `drop-in-visits` keeps working. But
Rover can introduce a slug nobody here has seen, and when that happens there are
two ways to be wrong:

- Treat it as needing access, and a door code goes to a sitter who is keeping the
  dog at their own house. The message also reads as a mistake, which is its own
  small damage to a working relationship.
- Treat it as not needing access, and a reminder does not arrive. You notice
  because the sitter messages you, and you send the code yourself.

The second is recoverable and the first is not, so unknown means no. Boarding and
day-care keywords are also checked *before* the access keywords, so a slug that
mentions both — `boarding-and-walking`, say — is read as boarding.

If you hit a service type that should be on this list, it is a one-line fix:
open an issue with the slug (the slug alone — not diagnostics, and not the
sitter's name).

## A note on the code itself

The code is never logged and never stored by this integration. It is passed to a
service, though, and **anything passed to any service call is recorded in that
automation's trace**, which is kept in your config directory and shown in the UI.
That is local to your instance, but it is a good reason to use a rotating guest
code rather than the code you use yourself.

If you send the reminder onward by SMS or a third-party push service, the code
passes through whatever that service is. That is a consideration for choosing the
notifier, not something this integration can fix on your behalf.
