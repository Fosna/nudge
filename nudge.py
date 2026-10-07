#!/usr/bin/env python3
"""nudge -- schedule a macOS notification that outlives this session.

    nudge in 10m "build done"
    nudge list
    nudge cancel <id>
    nudge status
"""

import argparse
import sys
import time

import install
import store
from timespec import BadDuration, humanize, parse_duration


def cmd_in(args):
    try:
        seconds = parse_duration(args.duration)
    except BadDuration as e:
        sys.exit("nudge: %s" % e)
    message = " ".join(args.message)
    job = store.add(message, time.time() + seconds, title=args.title)
    print("%s  in %s  %r" % (job["id"], humanize(seconds), message))


def cmd_list(args):
    now = time.time()
    jobs = store.jobs()
    if not jobs:
        print("(empty)")
        return
    for j in jobs:
        print("%s  in %s  %r" % (j["id"], humanize(j["fire_at"] - now), j["message"]))


def cmd_cancel(args):
    job = store.cancel(args.id)
    if job is None:
        sys.exit("nudge: no such job: %s" % args.id)
    print("cancelled %s  %r" % (job["id"], job["message"]))


def cmd_status(args):
    """Report whether a scheduled nudge would actually fire, and how to fix it.

    Lives on the CLI as well as on install.py so the Claude Code skill only ever
    has to know one command.
    """
    if install.cmd_status(args):
        sys.exit(1)


def build_parser():
    p = argparse.ArgumentParser(prog="nudge", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    p_in = sub.add_parser("in", help="schedule a notification after a delay")
    p_in.add_argument("duration", help="10m, 90s, 1h30m, or a bare number of minutes")
    p_in.add_argument("message", nargs="+")
    p_in.add_argument("--title", default="nudge")
    p_in.set_defaults(func=cmd_in)

    p_ls = sub.add_parser("list", help="show pending notifications")
    p_ls.set_defaults(func=cmd_list)

    p_rm = sub.add_parser("cancel", help="cancel a pending notification by id")
    p_rm.add_argument("id")
    p_rm.set_defaults(func=cmd_cancel)

    p_st = sub.add_parser("status", help="check that the daemon will fire scheduled nudges")
    p_st.set_defaults(func=cmd_status)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
