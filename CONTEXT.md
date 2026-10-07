# nudge — project context

macOS notification system. Claude Code sessions schedule notifications that fire later,
independent of whether the session is still alive.

## Decisions (locked)

- **Name:** `nudge`
- **Stack:** Python
- **Delivery:** `terminal-notifier`, fallback `osascript`
- **Scheduler:** long-running daemon + persistent job queue (survives session exit)
- **Interface:** CLI (`nudge in 10m "build done"`) + a Claude Code skill wrapping it
- **Process mgmt:** LaunchAgent keeps the daemon alive
- **Queue store:** JSON on disk
- **Install:** shim bootstrap — no path to the clone is committed; `install.py` resolves
  it at install time, so shipping to a new machine is `git clone` + `install.py install`
- **No code signing**

## CLI

```bash
nudge in 20m "stand up"    # also list, cancel <id>, status
```

Full reference in README.md — it is not duplicated here.

## Scaffold

Built:
- `nudge.py` — CLI (`in` / `list` / `cancel` / `status`)
- `nudge_daemon.py` — tick loop, fires due jobs. Sweeps every 15s by default;
  `NUDGE_TICK` overrides it, and must be set at install time (see below).
- `store.py` — JSON queue at `~/.nudge/queue.json` (`NUDGE_HOME` overrides). This is
  where scheduling lives.
- `timespec.py` — duration parsing and relative-time display
- `notify.py` — delivery only. Puts one notification on screen, synchronously, right
  now; it does not schedule and holds no state.
- `install.py` — install / uninstall / status for the shims, LaunchAgent and skill link
- `.claude/skills/nudge/SKILL.md` — the Claude Code skill wrapping the CLI
- `test_nudge.py` — 53 unittest cases
- `README.md` — Claude Code usage, install, design, troubleshooting, known gaps

`install.py install` generates four artifacts outside the repo: `~/.local/bin/nudge` and
`~/.local/bin/nudge-daemon` (shims execing this clone), the LaunchAgent plist (pointing
at the `nudge-daemon` shim), and `~/.claude/skills/nudge` symlinked to this clone's
skill, which is what makes the skill global. Re-run it after moving the clone.

## Cancellation

`nudge cancel <id>` removes a pending job from the queue. Once the daemon has delivered
a notification it cannot be recalled — it belongs to Notification Center at that point.
There is no API to take a banner back.

## Implementation notes

- Jobs store an absolute `fire_at` epoch, so restarts and lid-close need no re-derivation.
- `store.claim_due()` removes jobs before delivery — one job fires once, even across a restart.
- Durations must parse in full: `1m30` and `10x` are errors, never a silently wrong time.
- Bare number means minutes (`nudge in 10 "..."` = 10 minutes).
- Notification text is always passed as argv, never interpolated into a script body.
- Clock and sender are injectable (`run_once(now, send=...)`) so tests never sleep.
- `humanize()` rounds up, so a job just set for 20m lists as `20m`, not `19m59s`.
- `NUDGE_TICK` / `NUDGE_HOME` are captured into the plist's `EnvironmentVariables` at
  install time: launchd inherits nothing from the installing shell, so a shell-exported
  value would otherwise reach the CLI and not the daemon — leaving the daemon sweeping a
  different queue, or at a different interval, than the user configured.
- A bad `NUDGE_TICK` warns and falls back to 15s rather than raising; under `KeepAlive`,
  exiting on malformed config would be a restart loop.
- `install.strays()` matches on argv shape — a python interpreter invoked against a file
  named like the daemon — not a substring of the command. A substring test flags any
  shell or editor that merely mentions the filename, including the command doing the check.
- `pgrep -f "python3 nudge_daemon.py"` never matches: the command line carries the
  resolved framework interpreter path, not `python3`. Match the script name alone.
- `launchctl print` output is parsed on anchored line starts: a bare `pid =` substring
  match hits the `ppid = 1` line first.
- Shims carry a marker comment, so `uninstall` and `install` can tell a shim they wrote
  from an unrelated `nudge` on the PATH and refuse to clobber it. `write_shims()` checks
  every destination before writing any, so a refusal cannot half-install.
- `install.healthy()` checks the LaunchAgent's program still exists, not just that the
  job is loaded: a moved clone leaves a job `launchctl` reports as loaded until it next
  tries to start it.
- `nudge status` duplicates `install.py status` so the skill only needs one command; on
  an unhealthy install it prints a repair command carrying the clone path, which is known
  at runtime from the shim rather than from any committed file.

## Known gaps

- **Delivery is at-most-once (accepted).** `claim_due()` deletes jobs from the queue
  before `notify.send()` runs, so a daemon killed in that window loses them. The claim is
  per-tick and batched: if five jobs come due together and the daemon dies after the second
  send, the other three are gone, not just one. Chosen deliberately over at-least-once --
  a duplicate nudge is worse than a missed one here.
  *Troubleshooting:* "scheduled, never arrived, not in `nudge list`" = this window, not a bug
  in parsing or the LaunchAgent. *If this ever needs to change:* claim into an `inflight` list,
  delete after send, re-queue leftovers at daemon startup.
- Sleep/wake, Focus/DND and a real `terminal-notifier` binary are still unverified by hand.
- A hand-started daemon steals jobs from the managed one and fires them on its own
  interval. `nudge status` now reports strays, but nothing prevents one.

## Tick change (2026-10-07)

`NUDGE_TICK` added, default 15s (was a hard-coded 1s). Captured into the plist at
install time because launchd inherits nothing from the installing shell.

Verified by hand: with only the managed daemon running, three `nudge in 1s` samples
fired after 3s, 16s and 15s — consistent with a 15s sweep. `NUDGE_TICK=60 install`
writes `EnvironmentVariables` into the plist and the daemon reads 60.0.

Found while measuring: a daemon started by hand at the very start of the session was
still running and sweeping at 1s, draining the queue before the managed daemon saw it.
Earlier timing results in this project's history were measured against that process and
should not be trusted. `nudge status` now reports strays.

## Status

Shim bootstrap and configurable tick done. `python3 -m unittest test_nudge` → 53 pass, clean under
`-W error::ResourceWarning`.

Verified by hand on this machine:
- `install.py install` writes both shims, the plist and the skill symlink; `nudge`
  resolves on the PATH; `status` reports all four healthy.
- A nudge scheduled with the bare `nudge` command from outside the repo fired and the
  queue drained — the daemon runs under launchd (ppid 1), not the calling shell.
- `pgrep -fl nudge_daemon` now identifies the process, which `daemon.py` did not.
- The move case: the repo was copied to a temp dir, `install.py install` run from the
  copy repointed both shims and the skill symlink, a nudge scheduled from the copy
  fired, and re-installing from the real location restored everything. The plist needs
  no repointing -- it names the shim, whose path is stable, which is the reason for the
  indirection.
- `uninstall` removed all four artifacts, left `~/.nudge/` state alone, and is
  idempotent. A planted foreign `nudge` on the PATH and a planted real directory at
  `~/.claude/skills/nudge` were both refused rather than clobbered, and survived intact.
- Every command in README.md and SKILL.md was run verbatim.
- No committed file contains an absolute path into a home directory; swept with grep
  over every `.py` and `.md` in the repo.

Still unverified: sleep/wake, Focus/DND, a real `terminal-notifier` binary, whether a
banner visibly appears (needs human eyes), and a genuinely different machine.

Next step: nothing queued. Candidates are `at <time>`, crash-safe delivery, and the
unverified behaviour above.
