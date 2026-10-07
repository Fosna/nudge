"""Persistent JSON job queue.

One file, rewritten atomically under an flock, so the CLI and the daemon can
both touch it. Jobs hold an absolute `fire_at` epoch: a restart or a closed lid
never has to re-derive when a job was meant to go off.
"""

import contextlib
import fcntl
import json
import os
import secrets
import tempfile
import time

HOME = os.path.expanduser(os.environ.get("NUDGE_HOME", "~/.nudge"))
QUEUE = os.path.join(HOME, "queue.json")
LOCK = os.path.join(HOME, "queue.lock")


def _ensure_home():
    os.makedirs(HOME, exist_ok=True)


@contextlib.contextmanager
def _locked():
    _ensure_home()
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _read():
    try:
        with open(QUEUE) as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return []  # missing or truncated queue starts empty rather than crashing
    return data.get("jobs", []) if isinstance(data, dict) else []


def _write(jobs):
    _ensure_home()
    fd, tmp = tempfile.mkstemp(dir=HOME)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"version": 1, "jobs": jobs}, f, indent=2)
        os.replace(tmp, QUEUE)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def add(message, fire_at, title="nudge"):
    job = {
        "id": secrets.token_hex(3),
        "message": message,
        "title": title,
        "fire_at": float(fire_at),
        "created_at": time.time(),
    }
    with _locked():
        jobs = _read()
        jobs.append(job)
        _write(jobs)
    return job


def jobs():
    with _locked():
        return sorted(_read(), key=lambda j: j["fire_at"])


def cancel(job_id):
    with _locked():
        jobs_ = _read()
        kept = [j for j in jobs_ if j["id"] != job_id]
        if len(kept) == len(jobs_):
            return None
        _write(kept)
        return next(j for j in jobs_ if j["id"] == job_id)


def claim_due(now):
    """Remove and return every job due at `now`, so a job can only fire once."""
    with _locked():
        jobs_ = _read()
        due = [j for j in jobs_ if j["fire_at"] <= now]
        if due:
            _write([j for j in jobs_ if j["fire_at"] > now])
        return sorted(due, key=lambda j: j["fire_at"])
