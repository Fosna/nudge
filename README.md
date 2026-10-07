# nudge

Schedule a macOS notification from a Claude Code session and let the session end. The
notification still fires.

```console
$ nudge in 20m "stand up"
3f1a9c  in 20m  'stand up'
```

That line is the CLI's confirmation, not the notification. The first field is the job
id — keep it if you might want to cancel. Twenty minutes later the banner appears,
whether or not the shell that scheduled it is still open.

## In a Claude Code session

This is what the project is for. The skill is installed globally, so it works from any
project:

> **you:** deploy's going to take a while — nudge me in 20 minutes to check it
>
> **claude:** *(runs `nudge status`, then `nudge in 20m "check the deploy"`)*
> Scheduled for 20 minutes from now, id `3f1a9c`. It'll fire even if you close this
> session.

Twenty minutes later you get the banner, whether or not that session is still open.
Other things it handles:

> **you:** what reminders do I have pending?
>
> **claude:** *(runs `nudge list`)* One: `3f1a9c`, in about 6 minutes — "check the
> deploy".

> **you:** actually cancel that
>
> **claude:** *(runs `nudge list` to match the message, then `nudge cancel 3f1a9c`)*
> Cancelled.

> **you:** remind me at 3pm about the standup
>
> **claude:** *(works out that's 94 minutes away, runs `nudge in 94m "standup"`)*
> Set for 3pm.

Clock times work because the skill converts them to a delay — the CLI itself only
takes delays.

## Usage

```bash
nudge in 90s "tea"                 # seconds (rounded up to the next sweep)
nudge in 20m "stand up"            # minutes
nudge in 1h30m "meeting"           # combined
nudge in 10 "bare number is minutes"
nudge in 2h "deploy window" --title "ops"

nudge list                         # id, relative time, message
nudge cancel 3f1a9c                # by id from list
nudge status                       # is the daemon actually going to fire these?
```

Durations must parse completely. `1m30` and `10x` are errors rather than a silently
wrong time:

```console
$ nudge in 1m30 "oops"
nudge: bad duration: '1m30' (try 10m, 90s, 1h30m)
```

Pending nudges cancel cleanly. A notification already delivered cannot be recalled — at
that point it belongs to Notification Center.

There is no `at 15:00` yet. Convert to a delay, or let the skill do it for you.

## How it works

The CLI appends a job to a JSON queue on disk. A daemon under `launchd` wakes every 15
seconds, claims whatever is due, and delivers it. Nothing lives in the scheduling
process, so nothing depends on it staying alive.

```
nudge.py ──writes──▶ ~/.nudge/queue.json ──reads──▶ nudge_daemon.py ──▶ notification
                                                    (launchd keeps it running)
```

Jobs hold an absolute fire time, not a countdown, so a restart or a closed lid needs no
re-derivation.

### The sweep interval

The daemon sweeps every 15 seconds by default, so **a nudge can fire up to 15 seconds
late**. That is invisible for "remind me in 20 minutes" and significant for
`nudge in 5s`, which is why short delays are approximate.

Change it with `NUDGE_TICK`, in seconds:

```bash
NUDGE_TICK=60 python3 install.py install
```

It has to be set at install time, not in your shell. A `launchd` agent inherits nothing
from the terminal that installed it, so an exported `NUDGE_TICK` would reach the CLI and
never the daemon — `install` captures it into the plist instead. Same for `NUDGE_HOME`.
A malformed value is ignored with a warning in `~/.nudge/daemon.err`; the daemon runs
under `KeepAlive`, so exiting on bad config would be a restart loop.

## Install

Requires Python 3 and macOS. No dependencies.

```bash
git clone <repo> ~/anywhere/nudge
cd ~/anywhere/nudge
python3 install.py install
```

That resolves where the clone lives and writes four things:

| | |
|---|---|
| `~/.local/bin/nudge` | shim → this clone's `nudge.py` |
| `~/.local/bin/nudge-daemon` | shim → this clone's `nudge_daemon.py` |
| `~/Library/LaunchAgents/com.nudge.daemon.plist` | starts the daemon at login, restarts it if it dies |
| `~/.claude/skills/nudge` | symlink → this clone's skill, making it global |

No path to the clone is committed anywhere in the repo — it is resolved at install time.
So shipping to another machine is just clone-and-install, and **if you move the clone,
re-run `python3 install.py install`** from its new home to repoint everything.

`install` is idempotent. It refuses to overwrite a `nudge` on your PATH it did not write,
and it leaves an existing `~/.claude/skills/nudge` alone rather than clobbering it.

`~/.local/bin` needs to be on your PATH for the bare `nudge` command; install warns you
if it isn't.

For nicer notifications, `brew install terminal-notifier`. Without it `nudge` falls back
to `osascript`, which works but gives you Script Editor's icon and no click actions.

**Installing it is not enough.** macOS must also grant it permission, and until that
happens it exits 3 — `Could not request notification permission` — and delivers nothing.
`nudge` picks its sender by *outcome*, not by what is installed: a sender that exits
non-zero is retried with the next one, so an unpermitted `terminal-notifier` costs you a
wasted exec and nothing else. If every sender fails, the line lands in
`~/.nudge/daemon.err` — the job is already out of the queue by then, so that log is the
only trace it existed.

To grant it, register the bundle with LaunchServices once:

```bash
open -a "$(brew --prefix)/opt/terminal-notifier/terminal-notifier.app" --args -message hi
```

Running the binary directly will not do it — macOS reports `authorization not requested
yet` and never prompts, because the app was never launched as a registered app.
`terminal-notifier -diagnose` tells you which state you are in. After the prompt, allow
it, or flip it under System Settings > Notifications. Once permitted it carries its own sender
identity, which is what lets you set Alerts for nudge alone instead of for Script Editor.

## Sound and persistence

Nudges play `Ping` by default. Pick another from `/System/Library/Sounds`, or silence
them, at install time:

```bash
NUDGE_SOUND=Glass python3 install.py install   # Basso Blow Bottle Frog Funk Glass Hero
NUDGE_SOUND=none  python3 install.py install   # Morse Ping Pop Purr Sosumi Submarine Tink
```

Like `NUDGE_TICK`, it has to be set when you install — the daemon cannot see your shell.

**Whether a notification stays on screen is macOS's call, not nudge's.** There is no flag
for it; `terminal-notifier -timeout` is unrelated (it waits for an `-action` or `-reply`
response). Set it per app:

System Settings > Notifications > terminal-notifier > Alert Style > **Persistent**

On macOS 26 the choice is Temporary / Persistent; older versions call the same thing
Banners / Alerts. `terminal-notifier -diagnose` prints the style currently in effect.

## Troubleshooting

```bash
nudge status        # daemon, both shims, and the skill link
head -1 ~/.nudge/daemon.log   # what the daemon resolved at startup
```

That first log line names the tick, the sender, the sound and the queue path. If it says
`sender osascript (terminal-notifier not found)` while your shell finds the binary fine,
the daemon's PATH is the reason — re-run `python3 install.py install` from a shell that
can see it.

It exits non-zero and prints the repair command if the daemon won't fire. To find the
process yourself:

```bash
pgrep -fl nudge_daemon
launchctl print gui/$(id -u)/com.nudge.daemon | grep -E 'state|pid'
tail ~/.nudge/daemon.err
```

`status` checks that the daemon's program still exists, not just that `launchd` has the
job loaded — a clone that moved leaves a job `launchctl` happily calls loaded right up
until it next tries to start it.

It also reports **stray daemons**: a `nudge_daemon.py` started by hand outlives the shell
that started it, keeps sweeping the same queue, and fires jobs on its own interval. The
symptom is nudges arriving at the wrong time, or `NUDGE_TICK` appearing to have no
effect, while everything else looks healthy. `status` prints the pid and the `kill`.

When killing one, use the pid. A pattern like `pgrep -f "python3 nudge_daemon.py"` does
not match, because the command line carries the resolved interpreter path rather than
`python3` — that mismatch is exactly how a stray goes unnoticed.

## Files

| | |
|---|---|
| `nudge.py` | CLI: `in`, `list`, `cancel`, `status` |
| `nudge_daemon.py` | tick loop; fires due jobs |
| `store.py` | JSON queue, atomic writes under an flock |
| `timespec.py` | duration parsing and relative-time display |
| `notify.py` | delivers one notification: `terminal-notifier`, falling back to `osascript` |
| `install.py` | `install`, `uninstall`, `status` |
| `.claude/skills/nudge/SKILL.md` | the Claude Code skill |
| `test_nudge.py` | the test suite |

State lives in `~/.nudge/` — `queue.json`, plus `daemon.log` and `daemon.err`. Set
`NUDGE_HOME` to move it.

## Tests

```bash
python3 -m unittest test_nudge
```

The clock and the notification sender are injectable, so the suite never sleeps and
never shows a real banner. It never touches your real `~/.local/bin` or
`~/Library/LaunchAgents` either. Sleep/wake behaviour and Focus/Do Not Disturb are not
covered — check those by hand.

## Known gaps

- **At-most-once delivery.** Due jobs are removed from the queue before delivery,
  providing at-most-once delivery. There is an edge case where notifications don't fire:
  a daemon killed between the claim and the send loses them, and because the claim is
  batched per tick it can lose the whole batch. The alternative duplicates notifications
  on restart, which is the worse failure for a reminder. Practically: a nudge that never
  arrived *and* is gone from `nudge list` hit this window — it is not a parsing or
  LaunchAgent bug, so don't go looking there.
- **No `at <time>`.** Delays only, though the skill converts clock times for you.
- **Focus/DND behaviour is unverified** — macOS may hold or drop a banner silently.

## Uninstall

```bash
python3 install.py uninstall   # daemon, shims, skill link
rm -rf ~/.nudge                # and the queue, if you want it gone
```

`uninstall` removes only what it wrote: a foreign `nudge` on your PATH or a skill link
pointing outside this clone is left in place, and says so rather than skipping silently.

It never aborts half-way — a removal that fails is reported and the rest still runs —
and it **verifies afterwards**, checking the job is unloaded, no daemon survives, and
every file is gone. If anything is left it prints what, and exits non-zero. So the
`&&` above is load-bearing:

```bash
python3 install.py uninstall && rm -rf ~/.nudge
```

Without it you could delete the queue while a daemon is still reading it. The usual
cause is a `nudge_daemon.py` someone started by hand, which `launchctl` never managed
and uninstall therefore cannot stop.
