---
name: nudge
description: Schedule a macOS notification to fire later, even after this session ends. Use when the user asks to be reminded, pinged, or notified after a delay ("remind me in 20 minutes", "ping me when the build should be done", "nudge me at the end of the hour"), or asks to see or cancel pending reminders. Not for notifying at the end of the current turn — that is just a reply.
---

# nudge

A notification scheduled here is handed to a background daemon, so it fires whether or
not this session is still alive. Everything runs through the `nudge` command, which
`install.py` put on the PATH.

## Schedule one

```bash
nudge in 20m "stand up and stretch"
```

Duration is one token: `90s`, `20m`, `2h`, `1h30m`, or a bare number meaning minutes.
It must parse in full — `1m30` is an error, not 1 minute. Convert clock times yourself
(`date` gives the current time; "at 3pm" becomes the number of minutes until 3pm).

Add `--title` when the default `nudge` would be unhelpful on screen.

## Show and cancel

```bash
nudge list            # id, relative time, message
nudge cancel <id>     # takes an id from list
```

To cancel something the user describes rather than names, run `list` first and match
the message yourself — do not guess an id.

Pending nudges cancel cleanly. A notification already delivered cannot be recalled —
it belongs to Notification Center at that point.

## The daemon must be running

Nothing fires if it is not. Check before the first schedule in a session:

```bash
nudge status          # "daemon  loaded  pid NNNN (running)" is healthy
```

If it is unhealthy, `status` exits non-zero and prints the exact repair command,
including the path to the clone — run what it tells you. That is the documented setup
step, not a new decision, so do it without asking and mention that you did.

If `nudge` is not on the PATH at all, the project was never installed on this machine.
Say so rather than guessing a path: the fix is `python3 install.py install` from the
clone, and only the user knows where that is.

## Reporting back

Say when it will fire in the user's terms ("in 20 minutes", not an epoch) and keep the
id to hand in case they want it cancelled.
