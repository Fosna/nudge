"""Parsing of the duration token in `nudge in <duration> <message>`."""

import math
import re

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_PAIR = re.compile(r"(\d+)([smhd])")


class BadDuration(ValueError):
    pass


def parse_duration(token):
    """Return seconds for tokens like 10m, 90s, 1h30m, or a bare number of minutes.

    Rejects anything the grammar does not fully consume, so `1m30` and `10x`
    raise instead of quietly meaning `1m` and `10m`.
    """
    tok = token.strip().lower()
    if not tok:
        raise BadDuration("empty duration")

    if tok.isdigit():
        return int(tok) * 60  # bare number means minutes

    total = 0
    consumed = 0
    for m in _PAIR.finditer(tok):
        if m.start() != consumed:
            break
        total += int(m.group(1)) * _UNITS[m.group(2)]
        consumed = m.end()
    if consumed != len(tok) or total == 0:
        raise BadDuration("bad duration: %r (try 10m, 90s, 1h30m)" % token)
    return total


def humanize(seconds):
    """Short relative form for `nudge list`.

    Rounds up, so a job scheduled for 20m reads as `20m` rather than `19m59s`.
    """
    s = math.ceil(seconds)
    if s < 0:
        return "overdue"
    if s < 60:
        return "%ds" % s
    if s < 3600:
        return "%dm%ds" % divmod(s, 60) if s % 60 else "%dm" % (s // 60)
    h, rem = divmod(s, 3600)
    return "%dh%dm" % (h, rem // 60) if rem // 60 else "%dh" % h
