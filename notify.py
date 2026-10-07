"""macOS notification delivery: terminal-notifier, falling back to osascript."""

import shutil
import subprocess

_OSASCRIPT = [
    "osascript",
    "-e", "on run argv",
    "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
    "-e", "end run",
]


def command(title, message):
    """Build the argv for one notification.

    Both branches pass the text as separate arguments -- never interpolated
    into a script body -- so quotes and newlines in a message stay inert.
    """
    tn = shutil.which("terminal-notifier")
    if tn:
        return [tn, "-title", title, "-message", message]
    return _OSASCRIPT + [message, title]


def send(title, message, runner=subprocess.run):
    return runner(command(title, message), capture_output=True)
