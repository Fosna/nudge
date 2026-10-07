"""macOS notification delivery: terminal-notifier, falling back to osascript.

The fallback is driven by the *outcome*, not just by which binaries exist.
An installed `terminal-notifier` that has not been granted notification
permission exits non-zero and delivers nothing -- if availability alone chose
the sender, installing it would silently turn every nudge into a no-op.
"""

import os
import shutil
import subprocess

DEFAULT_SOUND = "Ping"  # a name from /System/Library/Sounds
SILENT = ("none", "off")

# Default for `sound=`: read NUDGE_SOUND. None already means silent, so the
# "not given" case needs a value of its own.
FROM_ENV = object()

# launchd gives an agent PATH=/usr/bin:/bin:/usr/sbin:/sbin and nothing else, so
# a Homebrew terminal-notifier is invisible to `which` inside the daemon even
# though it is on the PATH of every shell. The daemon would then quietly deliver
# through osascript -- same text, same sound, but attributed to Script Editor,
# so the notification style set on terminal-notifier would never apply.
EXTRA_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")


def find_notifier(env=None, which=shutil.which):
    """Locate terminal-notifier without trusting PATH.

    `NUDGE_NOTIFIER` wins: install.py resolves the binary in the installing
    shell and bakes the absolute path into the plist.
    """
    env = os.environ if env is None else env
    pinned = env.get("NUDGE_NOTIFIER")
    if pinned:
        return pinned if os.access(pinned, os.X_OK) else None
    found = which("terminal-notifier")
    if found:
        return found
    for directory in EXTRA_BIN_DIRS:
        candidate = os.path.join(directory, "terminal-notifier")
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def _default_which(name):
    return find_notifier() if name == "terminal-notifier" else shutil.which(name)


def _osascript(with_sound):
    body = "display notification (item 1 of argv) with title (item 2 of argv)"
    if with_sound:
        body += " sound name (item 3 of argv)"
    return ["osascript", "-e", "on run argv", "-e", body, "-e", "end run"]


def sound_name(env=None):
    """The sound to play, from `NUDGE_SOUND`.

    Unset or empty means the default; `none` or `off` means silent. Empty is
    not silent because install drops blank settings, so the daemon never sees one.
    """
    raw = ((os.environ if env is None else env).get("NUDGE_SOUND") or "").strip()
    if not raw:
        return DEFAULT_SOUND
    return None if raw.lower() in SILENT else raw


def commands(title, message, which=_default_which, sound=FROM_ENV):
    """Every way to deliver one notification, best first.

    Each form passes the text as separate arguments -- never interpolated into
    a script body -- so quotes and newlines in a message stay inert. That holds
    for the sound name too, which is why it is an argv item and not spliced into
    the AppleScript source.

    `sound` is a sound name, None for silent, or FROM_ENV to read `NUDGE_SOUND`.
    """
    sound = sound_name() if sound is FROM_ENV else sound
    forms = []
    tn = which("terminal-notifier")
    if tn:
        argv = [tn, "-title", title, "-message", message]
        if sound:
            argv += ["-sound", sound]
        forms.append(argv)
    forms.append(_osascript(bool(sound)) + [message, title] + ([sound] if sound else []))
    return forms


def send(title, message, runner=subprocess.run, which=_default_which, sound=FROM_ENV):
    """Deliver one notification, trying each form until one succeeds.

    Returns (argv, result) for the attempt that worked, or (None, [results])
    if every form failed -- the caller decides whether that is worth logging.
    """
    attempts = []
    for argv in commands(title, message, which=which, sound=sound):
        result = runner(argv, capture_output=True)
        code = getattr(result, "returncode", 0)
        if code == 0:
            return argv, result
        attempts.append((argv, result))
    return None, attempts


def describe_failure(attempts):
    """One line per failed sender, for the daemon log."""
    lines = []
    for argv, result in attempts:
        stderr = getattr(result, "stderr", b"") or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        lines.append("%s exited %s: %s" % (
            argv[0], getattr(result, "returncode", "?"), stderr.strip() or "(no stderr)"))
    return lines
