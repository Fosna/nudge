#!/usr/bin/env python3
"""nudge daemon -- fires due jobs, then forgets them.

Jobs are claimed out of the queue before delivery, so one job yields one
notification even across a restart. A job that came due while the daemon was
down (or the lid was shut) fires on the next tick rather than being dropped.

The sweep interval comes from `NUDGE_TICK` (default 15s). A job therefore fires
up to one tick late, which is why sub-tick delays are approximate.
"""

import math
import os
import sys
import time

import notify
import store

DEFAULT_TICK = 15.0


def tick_seconds(env=None):
    """Seconds between sweeps, from `NUDGE_TICK`.

    A bad value warns and falls back rather than raising: the daemon runs under
    KeepAlive, so exiting on malformed config would be a crash loop.
    """
    raw = (os.environ if env is None else env).get("NUDGE_TICK")
    if raw is None:
        return DEFAULT_TICK
    try:
        value = float(raw)
        if not math.isfinite(value) or value <= 0:
            raise ValueError
    except ValueError:
        print("nudge: ignoring bad NUDGE_TICK=%r, using %gs" % (raw, DEFAULT_TICK),
              file=sys.stderr)
        return DEFAULT_TICK
    return value


def _log_failure(job, outcome):
    """Record a nudge that no sender could deliver.

    The job is already out of the queue by now, so this line in `daemon.err` is
    the only trace it ever existed. Tolerates a `send` that returns anything
    other than notify's (argv, detail) pair, so test doubles stay simple.
    """
    if not (isinstance(outcome, tuple) and len(outcome) == 2 and outcome[0] is None):
        return
    for line in notify.describe_failure(outcome[1]):
        print("nudge: lost %r -- %s" % (job["message"], line), file=sys.stderr)


def run_once(now=None, send=notify.send):
    """Fire everything due at `now`. Returns the jobs fired."""
    now = time.time() if now is None else now
    due = store.claim_due(now)
    for job in due:
        _log_failure(job, send(job["title"], job["message"]))
    return due


def startup_banner(env=None):
    """What this daemon resolved, for the first line of `daemon.log`.

    launchd hands an agent a bare PATH, so a tool that every shell can find may
    be invisible here -- and delivery falls back silently. Printing the resolved
    sender turns "notifications behave oddly" into one line of log.
    """
    notifier = notify.find_notifier(env)
    return "nudge daemon: tick %gs, sender %s, sound %s, queue %s" % (
        tick_seconds(env),
        notifier or "osascript (terminal-notifier not found)",
        notify.sound_name(env) or "none",
        store.QUEUE,
    )


def run_forever(tick=None, clock=time.time, sleep=time.sleep, send=notify.send):
    print(startup_banner(), flush=True)
    tick = tick_seconds() if tick is None else tick
    while True:
        run_once(clock(), send=send)
        sleep(tick)


if __name__ == "__main__":
    run_forever()
