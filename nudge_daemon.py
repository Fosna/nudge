#!/usr/bin/env python3
"""nudge daemon -- fires due jobs, then forgets them.

Jobs are claimed out of the queue before delivery, so one job yields one
notification even across a restart. A job that came due while the daemon was
down (or the lid was shut) fires on the next tick rather than being dropped.

The sweep interval comes from `NUDGE_TICK` (default 15s). A job therefore fires
up to one tick late, which is why sub-tick delays are approximate.
"""

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
        if value <= 0:
            raise ValueError
    except ValueError:
        print("nudge: ignoring bad NUDGE_TICK=%r, using %gs" % (raw, DEFAULT_TICK),
              file=sys.stderr)
        return DEFAULT_TICK
    return value


def run_once(now=None, send=notify.send):
    """Fire everything due at `now`. Returns the jobs fired."""
    now = time.time() if now is None else now
    due = store.claim_due(now)
    for job in due:
        send(job["title"], job["message"])
    return due


def run_forever(tick=None, clock=time.time, sleep=time.sleep, send=notify.send):
    tick = tick_seconds() if tick is None else tick
    while True:
        run_once(clock(), send=send)
        sleep(tick)


if __name__ == "__main__":
    run_forever()
