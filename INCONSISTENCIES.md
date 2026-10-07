# Inconsistencies

Repo scan, 2026-10-07. Items keep their original numbers so earlier references still work.
Line references are current as of the fixes below.

| Category | Open | Fixed | Open # | Fixed # |
|---|---|---|---|---|
| Behaviour bugs | #9, #16 | #10, #12, #14, #15 | 2 | 4 |
| Wrong or stale docs | #2, #3, #6, #7, #11 | #1, #4, #5 | 5 | 3 |
| Duplicated logic and hidden rules | #13, #17, #24 | — | 3 | 0 |
| Test hygiene | #18, #19, #20, #21 | — | 4 | 0 |
| Cosmetic | #8, #22, #23 | — | 3 | 0 |
| **Total** | | | **17** | **7** |

Focus/DND stays an open, unverified item; it is not tracked here.

### Severity

Rated by user impact. Fixed items (✓) are rated as they were before the fix.

- **High:** wrong behaviour a user will run into.
- **Medium:** misleads people, or could hide failures.
- **Low:** wording, style or internal duplication.

| Category | High | Medium | Low |
|---|---|---|---|
| Behaviour bugs | 2 (#14 ✓, #15 ✓) | 3 (#9, #10 ✓, #12 ✓) | 1 (#16) |
| Wrong or stale docs | 0 | 1 (#4 ✓) | 7 (#1 ✓, #2, #3, #5 ✓, #6, #7, #11) |
| Duplicated logic and hidden rules | 0 | 0 | 3 (#13, #17, #24) |
| Test hygiene | 0 | 2 (#18, #19) | 2 (#20, #21) |
| Cosmetic | 0 | 0 | 3 (#8, #22, #23) |
| **Total** | **2** (0 open) | **6** (3 open) | **16** (14 open) |

Nothing rated High is still open. The open Medium items, #9, #18 and #19, are the next
to fix.

## Behaviour bugs

The program does the wrong thing.

### Open

9. **`install.py status` and `nudge status` behave differently.** README says `status` exits
   non-zero when the daemon won't fire, and lists `status` under `install.py`
   (`README.md:222`). Only `nudge status` does that; `install.py`'s `cmd_status`
   (`install.py:406`) always exits 0.
16. **`nudge status` gives the same message for every failure.** `nudge.py:54` always says
    "the daemon is not running", even when the real state is "not installed" or "program is
    gone".

Both are in `status`, so they could be one small change.

### Fixed

10. **A bad `NUDGE_TICK` could cause a restart loop.** `tick_seconds` accepted `nan` and
    `inf`, then `time.sleep` raised, so launchd kept restarting the daemon. Nudges still
    fired (each restart swept the queue first), but the logs grew every 10s and `status`
    reported healthy. It now rejects values that aren't finite and falls back to 15s.
12. **An empty `NUDGE_SOUND` meant two different things.** `notify.sound_name` treated `""`
    as silent, but `install.daemon_env` drops empty values, so the daemon played Ping. Now
    empty means the default everywhere; only `none` or `off` is silent.
14. **The repair command broke on paths with spaces.** `repair_command()` hard-coded
    `python3` and didn't quote the path. It now uses `sys.executable` and `_quote()`, like
    the shims. This mattered because SKILL.md tells Claude to run it without asking.
15. **`status` could tell you to kill an unrelated process.** The old `daemon.py` name
    matched any Python process running a file with that name. Only `nudge_daemon.py` is
    matched now.

## Wrong or stale docs

The docs say something untrue. Each open item is a one-line edit.

### Open

2. **The `install.py` docstring has the wrong count.** `install.py:9` says "three generated
   artifacts" but lists four. The README and `CONTEXT.md:51` both say four.
3. **The uninstall check has a third count.** `CONTEXT.md:44` says uninstall "re-checks all
   five artefacts". `survivors()` (`install.py:226`) actually checks six things: the loaded
   job, stray daemons, the plist, two shims and the skill link. The same line also spells it
   "artefacts" while the rest of the repo uses "artifacts".
6. **Days (`d`) aren't documented.** `timespec.py:6` accepts days and a test covers `1d2h`,
   but the README, SKILL.md and the `--help` text (`nudge.py:64`) only mention s, m and h.
7. **README says "the `&&` above is load-bearing", but the `&&` is below.** At
   `README.md:265`, the block above (`:254–256`) runs the two commands on separate lines.
   The `&&` only appears in the block underneath.
11. **The `timespec.py` docstring is too narrow.** `:1` says "Parsing of the duration token",
    but the module also contains `humanize()`, as the README says.

### Fixed

1. **The test count was out of date.** `CONTEXT.md` said 53 tests. The counts are removed,
   and `CONTEXT.md` now tells agents to run the suite before calling any change done.
4. **`CONTEXT.md` listed confirmed behaviour as unverified.** The "Still unverified" list
   and the Focus/DND line now match what was confirmed on 2026-10-07.
5. **A known gap in `CONTEXT.md` was already closed.** It said `terminal-notifier` "would"
   give nudge its own sender identity; it now says it does. The Script Editor screenshot is
   labelled as delivery through the osascript fallback.

## Duplicated logic and hidden rules

Works today, but could drift or mislead. Low priority.

13. **Two different ways to find `terminal-notifier`.** `install.daemon_env`
    (`install.py:77`) uses only `shutil.which`. `notify.find_notifier` also checks
    `/opt/homebrew/bin` and `/usr/local/bin`, and checks that the binary is executable. The
    install step could just call `find_notifier`.
17. **Repeated launchctl target.** `"%s/%s" % (_domain(), LABEL)` is built four times in
    `install.py` (`:116`, `:182`, `:250`, `:369`).
24. **Hidden meaning for `sound=False`.** In `notify.commands`, `False` means "read it from the
    environment" and `None` means "silent", and no docstring says so.

## Test hygiene

#18 first: a leaked setting can hide failures in later tests.

18. **`StoreCase` leaks an environment variable.** It sets `os.environ["NUDGE_HOME"]`
    (`test_nudge.py:56`) and never restores it, so later tests and modules see a temp
    directory that has already been deleted.
19. **A test depends on the machine.** `test_plist_paths_are_absolute`
    (`test_nudge.py:528`) calls `plist_body()` without `env` or `which_binary`, so it uses
    the real environment and the real `shutil.which`.
20. **The test run prints install output.** `cmd_uninstall` writes to stdout during tests
    ("uninstalled. State in /var/folders/…"), which clutters the results.
21. **Some edge cases have no tests:** `install.py status`'s exit code (#9) and `command()`.
    `command()` is "kept for callers", but its only caller is a test (`test_nudge.py:401`).
    (`nan`/`inf` ticks and an empty `NUDGE_SOUND` are now covered.)

## Cosmetic

Wording and formatting. Low priority.

8. **README's sound list is split confusingly.** At `README.md:164–165`, the list of sound
   names runs across both comment lines, so the second half sits next to `NUDGE_SOUND=none`
   and looks like it describes that line.
22. **Mixed dashes.** Code comments use `--` and the docs use `—`, and `CONTEXT.md` mixes both
    (`:118` and `:179` use `--`).
23. **Unclear "It".** At `README.md:191`, "It exits non-zero…" follows the `head -1` command,
    but it refers to `nudge status`.
