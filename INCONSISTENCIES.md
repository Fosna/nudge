# Inconsistencies

Repo scan, 2026-10-07. **21/27 fixed, 1 skipped.** Items keep their original numbers so
earlier references still work. Line references are current as of the fixes below.

Counts are **fixed/found**: `2/2` means everything found is fixed. Skipped items are
decided against, not fixed, so they stay out of the fixed count.

| Category | Fixed/found | Open | Fixed | Skipped |
|---|---|---|---|---|
| Behaviour bugs | 6/6 | — | #9, #10, #12, #14, #15, #16 | — |
| Wrong or stale docs | 10/11 | — | #1, #2, #3, #4, #5, #7, #11, #25, #26, #27 | #6 |
| Duplicated logic and hidden rules | 0/3 | #13, #17, #24 | — | — |
| Test hygiene | 2/4 | #20, #21 | #18, #19 | — |
| Cosmetic | 3/3 | — | #8, #22, #23 | — |
| **Total** | **21/27** | | | **1** |

Focus/DND stays an open, unverified item; it is not tracked here.

### Severity

Rated by user impact. Fixed items (✓) are rated as they were before the fix; skipped items
are marked ⊘.

- **High:** wrong behaviour a user will run into.
- **Medium:** misleads people, or could hide failures.
- **Low:** wording, style or internal duplication.

Each cell is **fixed/found**, then the items. `—` means nothing found.

| Category | High | Medium | Low |
|---|---|---|---|
| Behaviour bugs | 2/2 (#14 ✓, #15 ✓) | 3/3 (#9 ✓, #10 ✓, #12 ✓) | 1/1 (#16 ✓) |
| Wrong or stale docs | — | 1/1 (#4 ✓) | 9/10 (#1 ✓, #2 ✓, #3 ✓, #5 ✓, #7 ✓, #11 ✓, #25 ✓, #26 ✓, #27 ✓, #6 ⊘) |
| Duplicated logic and hidden rules | — | — | 0/3 (#13, #17, #24) |
| Test hygiene | — | 2/2 (#18 ✓, #19 ✓) | 0/2 (#20, #21) |
| Cosmetic | — | — | 3/3 (#8 ✓, #22 ✓, #23 ✓) |
| **Total** | **2/2** | **6/6** | **13/19** |

Every High and Medium item is fixed. All 5 open items are Low.

## Behaviour bugs (6/6)

The program does the wrong thing.

### Fixed

- **#9: `install.py status` and `nudge status` behaved differently.** README says `status`
  exits non-zero when nothing would fire, but `install.py status` always exited 0. Both
  now run `install.cmd_status`, which exits 1 and prints the repair command.
- **#10: A bad `NUDGE_TICK` could cause a restart loop.** `tick_seconds` accepted `nan` and
  `inf`, then `time.sleep` raised, so launchd kept restarting the daemon. Nudges still
  fired (each restart swept the queue first), but the logs grew every 10s and `status`
  reported healthy. It now rejects values that aren't finite and falls back to 15s.
- **#12: An empty `NUDGE_SOUND` meant two different things.** `notify.sound_name` treated `""`
  as silent, but `install.daemon_env` drops empty values, so the daemon played Ping. Now
  empty means the default everywhere; only `none` or `off` is silent.
- **#14: The repair command broke on paths with spaces.** `repair_command()` hard-coded
  `python3` and didn't quote the path. It now uses `sys.executable` and `_quote()`, like
  the shims. This mattered because SKILL.md tells Claude to run it without asking.
- **#15: `status` could tell you to kill an unrelated process.** The old `daemon.py` name
  matched any Python process running a file with that name. Only `nudge_daemon.py` is
  matched now.
- **#16: `nudge status` gave the same message for every failure.** It always said "the daemon
  is not running". `install.problem()` now names the actual reason: not installed,
  unreadable plist, program gone, or not loaded.

## Wrong or stale docs (10/11)

The docs say something untrue. Rule from the fixes: don't write counts of things into the
docs ("four artifacts", "53 tests"). They go stale every time the list changes.

### Fixed

- **#1: The test count was out of date.** `CONTEXT.md` said 53 tests. The counts are removed,
  and `CONTEXT.md` now tells agents to run the suite before calling any change done.
- **#2: The `install.py` docstring had the wrong count.** It said "three generated artifacts"
  and listed four. The count is removed.
- **#3: The uninstall check had a third count.** `CONTEXT.md` said "five artefacts"; the
  check covers six things. The count is removed, along with the other artifact counts in
  README.md, CONTEXT.md and `install.py` ("four things", "all four", "both shims").
- **#4: `CONTEXT.md` listed confirmed behaviour as unverified.** The "Still unverified" list
  and the Focus/DND line now match what was confirmed on 2026-10-07.
- **#5: A known gap in `CONTEXT.md` was already closed.** It said `terminal-notifier` "would"
  give nudge its own sender identity; it now says it does. The Script Editor screenshot is
  labelled as delivery through the osascript fallback.
- **#7: README said "the `&&` above is load-bearing", but the `&&` was below.** The
  Uninstall block now shows `uninstall && rm -rf ~/.nudge` itself, and the duplicate block
  underneath is gone.
- **#11: The `timespec.py` docstring was too narrow.** It only mentioned parsing; it now
  covers `humanize()` too.
- **#25: `CONTEXT.md` still described `install.healthy()` as the health check.** Found in a
  second docs pass, after #16 moved the logic into `install.problem()`. It now describes
  `problem()`, and that both `status` commands exit 1 with the reason.
- **#26: The `notify.py` entry in `CONTEXT.md` said the same thing twice.** "Chooses its
  sender by outcome" and "falls back on a non-zero exit" were both there. Merged.
- **#27: The empty-`NUDGE_SOUND` rule from #12 wasn't documented.** README and `CONTEXT.md`
  now say empty means the default, and that `off` silences as well as `none`.

### Skipped

- **#6: Days (`d`) aren't documented.** `timespec.py:6` accepts days and a test covers
  `1d2h`, but the README, SKILL.md and `--help` only mention s, m and h. Decided against
  documenting it; days stay a hidden extra.

## Duplicated logic and hidden rules (0/3)

Works today, but could drift or mislead. Low priority.

- **#13: Two different ways to find `terminal-notifier`.** `install.daemon_env`
  (`install.py:77`) uses only `shutil.which`. `notify.find_notifier` also checks
  `/opt/homebrew/bin` and `/usr/local/bin`, and checks that the binary is executable. The
  install step could just call `find_notifier`.
- **#17: Repeated launchctl target.** `"%s/%s" % (_domain(), LABEL)` is built four times in
  `install.py` (`:116`, `:182`, `:250`, `:382`).
- **#24: Hidden meaning for `sound=False`.** In `notify.commands`, `False` means "read it from the
  environment" and `None` means "silent", and no docstring says so.

## Test hygiene (2/4)

### Open

- **#20: The test run prints install output.** `cmd_uninstall` writes to stdout during tests
  ("uninstalled. State in /var/folders/…"), which clutters the results.
- **#21: `command()` has no real caller.** It is "kept for callers", but its only caller is a
  test (`test_nudge.py:407`). (The other gaps listed here are now covered: `nan`/`inf`
  ticks, an empty `NUDGE_SOUND`, and the `status` exit code.)

### Fixed

- **#18: `StoreCase` leaked `NUDGE_HOME`.** It set `os.environ["NUDGE_HOME"]` and never restored
  it, so later tests saw a deleted temp folder and your own setting was overwritten. It
  now uses `mock.patch.dict` and reloads `store` after the environment is restored.
- **#19: A test depended on the machine.** `test_plist_paths_are_absolute` called
  `plist_body()` with the real environment and `shutil.which`. It now passes `env={}` and
  `which_binary`, like the other plist tests.

## Cosmetic (3/3)

Wording and formatting. Low priority.

### Fixed

- **#8: README's sound list was split confusingly** across two comment lines. The list is
  gone; README now says to run `ls /System/Library/Sounds`, which can't go stale.
- **#23: Unclear "It".** README's "It exits non-zero…" followed a log command but meant
  `nudge status`. It now names `nudge status` and says it prints the reason.
- **#22: Mixed dashes.** `CONTEXT.md` used `--` in two places among `—`. Both are `—` now.
  The convention: code and its comments use ASCII `--`, the Markdown docs use `—`.
