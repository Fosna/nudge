"""macOS notification delivery: terminal-notifier, falling back to osascript.

When peon-ping is installed, a nudge also gets its large on-screen overlay and a
peon voice line. The banner is still posted, silently, so Notification Center
keeps a record of a reminder whose overlay was clicked away.

The fallback is driven by the *outcome*, not just by which binaries exist.
An installed `terminal-notifier` that has not been granted notification
permission exits non-zero and delivers nothing -- if availability alone chose
the sender, installing it would silently turn every nudge into a no-op.
"""

import json
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


PEON_DIR = os.path.expanduser("~/.claude/hooks/peon-ping")
PEON_LINE = os.path.join("packs", "peon", "sounds", "PeonWhat4.wav")  # "Something need doing?"
OVERLAY_COLOR = "blue"
DEFAULT_VOLUME = 0.5

# peon-ping stacks its own overlays in slots 0-4, one row each from the top, and
# a click on any overlay dismisses every overlay sharing its slot. Starting below
# them keeps a nudge out of both peon's rows and its dismiss channel.
SLOTS = range(5, 10)

# Overlays and sounds still running. The daemon lives for days, so children are
# reaped here; a slot is free again once its overlay has been clicked away.
_overlays = {}
_children = []

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


def find_peon(env=None):
    """peon-ping's install dir if its overlays should be used, else None.

    `NUDGE_STYLE=banner` opts out; `NUDGE_PEON_DIR` points at a non-default
    install. A missing overlay script means "not installed", not an error.
    """
    env = os.environ if env is None else env
    if (env.get("NUDGE_STYLE") or "").strip().lower() == "banner":
        return None
    home = env.get("NUDGE_PEON_DIR") or PEON_DIR
    return home if os.path.isfile(os.path.join(home, "scripts", "mac-overlay.js")) else None


def _peon_config(home):
    try:
        with open(os.path.join(home, "config.json")) as f:
            config = json.load(f)
        return config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        return {}


def overlay_script(home, config=None):
    """The overlay for peon-ping's configured theme, else its default one."""
    config = _peon_config(home) if config is None else config
    theme = config.get("overlay_theme")
    if theme in ("jarvis", "glass", "sakura"):
        themed = os.path.join(home, "scripts", "mac-overlay-%s.js" % theme)
        if os.path.isfile(themed):
            return themed
    return os.path.join(home, "scripts", "mac-overlay.js")


def overlay_command(title, message, slot, position="top-center"):
    """osascript argv for one overlay; the script itself arrives on stdin.

    The script is piped rather than named because peon-ping kills any process
    whose command line mentions `mac-overlay` once it is a minute old -- a nudge
    left waiting for its click would vanish the next time peon-ping spoke.
    Dismiss 0 keeps the overlay up until clicked, which also closes it.
    """
    # message color icon slot dismiss bundle ide_pid tty subtitle position type all_screens
    return ["osascript", "-l", "JavaScript", "-", message, OVERLAY_COLOR, "", str(slot),
            "0", "", "0", "", title, position, "", "false"]


def _volume(config):
    try:
        return min(max(float(config.get("volume", DEFAULT_VOLUME)), 0.0), 1.0)
    except (TypeError, ValueError):
        return DEFAULT_VOLUME


def _reap():
    for slot, proc in list(_overlays.items()):
        if proc.poll() is not None:
            del _overlays[slot]
    _children[:] = [p for p in _children if p.poll() is None]


def _free_slot():
    _reap()
    return next((s for s in SLOTS if s not in _overlays), SLOTS[0])


def show_peon(title, message, home, with_sound=True, spawn=subprocess.Popen):
    """Start the overlay and voice line without waiting. False if it could not start.

    Both run in their own session, so they are neither blocked on by the daemon
    nor killed with it when launchd restarts the job.
    """
    config = _peon_config(home)
    slot = _free_slot()
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
             "start_new_session": True}
    try:
        with open(overlay_script(home, config), "rb") as script:
            argv = overlay_command(title, message, slot,
                                   config.get("notification_position") or "top-center")
            _overlays[slot] = spawn(argv, stdin=script, **quiet)
    except OSError:
        return False
    line = os.path.join(home, PEON_LINE)
    if with_sound and os.path.isfile(line):
        try:
            _children.append(spawn(["afplay", "-v", "%g" % _volume(config), line],
                                   stdin=subprocess.DEVNULL, **quiet))
        except OSError:
            pass  # the overlay is up; a missing voice line is not worth a banner sound
    return True


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


def send(title, message, runner=subprocess.run, which=_default_which, sound=FROM_ENV,
         peon=FROM_ENV, spawn=subprocess.Popen):
    """Deliver one notification, trying each form until one succeeds.

    `peon` is peon-ping's install dir, None for banner only, or FROM_ENV to look
    it up. When its overlay starts, the voice line replaces the banner's sound.

    Returns (argv, result) for the attempt that worked, or (None, [results])
    if every form failed -- the caller decides whether that is worth logging.
    """
    sound = sound_name() if sound is FROM_ENV else sound
    peon = find_peon() if peon is FROM_ENV else peon
    if peon and show_peon(title, message, peon, with_sound=bool(sound), spawn=spawn):
        sound = None
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
