"""Tests for the nudge core. No sleeping, no real notifications."""

import importlib
import os
import tempfile
import time
import unittest

import timespec


class _StopLoop(Exception):
    """Breaks out of the daemon's forever-loop in tests."""


class TestDuration(unittest.TestCase):
    def test_units(self):
        self.assertEqual(timespec.parse_duration("90s"), 90)
        self.assertEqual(timespec.parse_duration("10m"), 600)
        self.assertEqual(timespec.parse_duration("2h"), 7200)
        self.assertEqual(timespec.parse_duration("1h30m"), 5400)
        self.assertEqual(timespec.parse_duration("1d2h"), 93600)

    def test_bare_number_is_minutes(self):
        self.assertEqual(timespec.parse_duration("10"), 600)

    def test_case_and_whitespace(self):
        self.assertEqual(timespec.parse_duration(" 10M "), 600)

    def test_rejects_partial_parses(self):
        # the failure that would silently fire at the wrong time
        for bad in ["1m30", "10x", "m10", "", "0s", "abc", "10 m"]:
            with self.subTest(bad=bad):
                with self.assertRaises(timespec.BadDuration):
                    timespec.parse_duration(bad)


class TestHumanize(unittest.TestCase):
    def test_rounds_up_so_a_fresh_job_reads_whole(self):
        self.assertEqual(timespec.humanize(1199.4), "20m")

    def test_forms(self):
        self.assertEqual(timespec.humanize(45), "45s")
        self.assertEqual(timespec.humanize(600), "10m")
        self.assertEqual(timespec.humanize(630), "10m30s")
        self.assertEqual(timespec.humanize(7200), "2h")
        self.assertEqual(timespec.humanize(5400), "1h30m")

    def test_past_due(self):
        self.assertEqual(timespec.humanize(-5), "overdue")


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["NUDGE_HOME"] = self.tmp.name
        import store
        self.store = importlib.reload(store)
        self.addCleanup(self.tmp.cleanup)


class TestStore(StoreCase):
    def test_add_list_cancel(self):
        job = self.store.add("build done", time.time() + 60)
        self.assertEqual([j["id"] for j in self.store.jobs()], [job["id"]])
        self.assertEqual(self.store.cancel(job["id"])["message"], "build done")
        self.assertEqual(self.store.jobs(), [])

    def test_cancel_unknown_id(self):
        self.assertIsNone(self.store.cancel("nope"))

    def test_survives_reload(self):
        self.store.add("persisted", time.time() + 60)
        self.store = importlib.reload(self.store)
        self.assertEqual(len(self.store.jobs()), 1)

    def test_listed_in_fire_order(self):
        now = time.time()
        late = self.store.add("late", now + 300)
        soon = self.store.add("soon", now + 10)
        self.assertEqual([j["id"] for j in self.store.jobs()], [soon["id"], late["id"]])

    def test_truncated_queue_recovers(self):
        self.store.add("doomed", time.time() + 60)
        with open(self.store.QUEUE, "w") as f:
            f.write("{not json")
        self.assertEqual(self.store.jobs(), [])

    def test_missing_queue_is_empty(self):
        self.assertEqual(self.store.jobs(), [])

    def test_claim_due_takes_only_past_due(self):
        now = 1000.0
        past = self.store.add("past", now - 1)
        self.store.add("future", now + 1)
        self.assertEqual([j["id"] for j in self.store.claim_due(now)], [past["id"]])
        self.assertEqual([j["message"] for j in self.store.jobs()], ["future"])

    def test_claim_due_is_exactly_once(self):
        self.store.add("once", 500.0)
        self.assertEqual(len(self.store.claim_due(1000.0)), 1)
        self.assertEqual(self.store.claim_due(1000.0), [])


class TestDaemon(StoreCase):
    def setUp(self):
        super().setUp()
        import nudge_daemon
        self.daemon = importlib.reload(nudge_daemon)
        self.sent = []

    def send(self, title, message):
        self.sent.append((title, message))

    def test_fires_due_job_once(self):
        self.store.add("build done", 500.0)
        self.daemon.run_once(1000.0, send=self.send)
        self.daemon.run_once(1001.0, send=self.send)
        self.assertEqual(self.sent, [("nudge", "build done")])

    def test_leaves_future_job_alone(self):
        self.store.add("later", 2000.0)
        self.daemon.run_once(1000.0, send=self.send)
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.store.jobs()), 1)

    def test_tick_defaults_to_15s(self):
        self.assertEqual(self.daemon.tick_seconds({}), 15.0)

    def test_tick_reads_env(self):
        self.assertEqual(self.daemon.tick_seconds({"NUDGE_TICK": "30"}), 30.0)
        self.assertEqual(self.daemon.tick_seconds({"NUDGE_TICK": "0.5"}), 0.5)

    def test_bad_tick_falls_back_instead_of_crashlooping(self):
        # the daemon runs under KeepAlive, so raising here would be a crash loop
        import contextlib, io
        for bad in ["nope", "0", "-5", ""]:
            with self.subTest(bad=bad), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(self.daemon.tick_seconds({"NUDGE_TICK": bad}), 15.0)
            if bad:
                self.assertIn("NUDGE_TICK", err.getvalue())

    def test_run_forever_uses_the_configured_tick(self):
        slept = []

        def sleep(seconds):
            slept.append(seconds)
            raise _StopLoop

        with self.assertRaises(_StopLoop):
            self.daemon.run_forever(clock=lambda: 0.0, sleep=sleep, send=self.send)
        self.assertEqual(slept, [15.0])

    def test_lost_notification_is_logged(self):
        import contextlib, io, notify
        self.store.add("vanished", 500.0)
        failed = (None, [(["terminal-notifier"], type("R", (), {"returncode": 3,
                                                               "stderr": b"not allowed"})())])
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.daemon.run_once(1000.0, send=lambda t, m: failed)
        self.assertIn("lost 'vanished'", err.getvalue())
        self.assertIn("not allowed", err.getvalue())

    def test_simple_send_double_is_not_treated_as_failure(self):
        import contextlib, io
        self.store.add("fine", 500.0)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.daemon.run_once(1000.0, send=self.send)
        self.assertEqual(err.getvalue(), "")

    def test_startup_banner_names_the_resolved_sender(self):
        line = self.daemon.startup_banner(
            {"NUDGE_NOTIFIER": "/opt/homebrew/bin/terminal-notifier"})
        self.assertIn("terminal-notifier", line)

    def test_startup_banner_admits_the_fallback(self):
        # the line that would have caught the PATH bug in one read
        line = self.daemon.startup_banner({"NUDGE_NOTIFIER": "/gone/terminal-notifier"})
        self.assertIn("osascript", line)
        self.assertIn("not found", line)

    def test_startup_banner_reports_tick_and_sound(self):
        line = self.daemon.startup_banner({"NUDGE_TICK": "30", "NUDGE_SOUND": "none"})
        self.assertIn("tick 30s", line)
        self.assertIn("sound none", line)

    def test_overdue_backlog_fires_on_next_tick(self):
        # daemon was down, or the lid was shut, past both fire times
        self.store.add("a", 100.0)
        self.store.add("b", 200.0)
        self.daemon.run_once(9999.0, send=self.send)
        self.assertEqual([m for _, m in self.sent], ["a", "b"])


class TestDaemonEnv(StoreCase):
    def setUp(self):
        super().setUp()
        import install
        self.install = importlib.reload(install)

    def test_settings_are_baked_into_the_plist(self):
        # launchd inherits nothing from the installing shell
        body = self.install.plist_body(env={"NUDGE_TICK": "30", "NUDGE_HOME": "/tmp/q"},
                                       which_binary=lambda n: None)
        self.assertEqual(body["EnvironmentVariables"],
                         {"NUDGE_TICK": "30", "NUDGE_HOME": "/tmp/q"})

    def test_no_env_block_when_nothing_is_set(self):
        self.assertNotIn("EnvironmentVariables",
                         self.install.plist_body(env={}, which_binary=lambda n: None))

    def test_blank_values_are_not_propagated(self):
        body = self.install.plist_body(env={"NUDGE_TICK": "", "NUDGE_HOME": "/tmp/q"},
                                       which_binary=lambda n: None)
        self.assertEqual(body["EnvironmentVariables"], {"NUDGE_HOME": "/tmp/q"})

    def test_notifier_path_is_pinned_into_the_plist(self):
        # resolved in the installing shell, because the daemon's PATH cannot find it
        body = self.install.plist_body(env={}, which_binary=lambda n: "/opt/homebrew/bin/" + n)
        self.assertEqual(body["EnvironmentVariables"]["NUDGE_NOTIFIER"],
                         "/opt/homebrew/bin/terminal-notifier")

    def test_no_notifier_pinned_when_none_installed(self):
        body = self.install.plist_body(env={}, which_binary=lambda n: None)
        self.assertNotIn("NUDGE_NOTIFIER", body.get("EnvironmentVariables", {}))

    def test_sound_is_propagated(self):
        body = self.install.plist_body(env={"NUDGE_SOUND": "Glass"},
                                       which_binary=lambda n: None)
        self.assertEqual(body["EnvironmentVariables"], {"NUDGE_SOUND": "Glass"})

    def test_sound_disabled_is_propagated_not_dropped(self):
        # "none" must reach the daemon, or it silently keeps the default
        body = self.install.plist_body(env={"NUDGE_SOUND": "none"},
                                       which_binary=lambda n: None)
        self.assertEqual(body["EnvironmentVariables"], {"NUDGE_SOUND": "none"})

    def test_unrelated_env_is_not_propagated(self):
        body = self.install.plist_body(env={"PATH": "/nope", "NUDGE_TICK": "5"},
                                       which_binary=lambda n: None)
        self.assertEqual(body["EnvironmentVariables"], {"NUDGE_TICK": "5"})


class TestStrays(StoreCase):
    """A hand-started daemon sweeping the same queue invalidates NUDGE_TICK."""

    TABLE = [
        (10, "/usr/bin/Python /repo/nudge_daemon.py"),
        (11, "/usr/bin/Python daemon.py"),             # legacy name, still sweeping
        (12, "/usr/bin/python3 /managed/nudge_daemon.py"),
        (20, "vim nudge_daemon.py.swp"),
        (21, "/bin/zsh -c eval python3 ... nudge_daemon.py ..."),
        (22, "grep -n nudge_daemon.py install.py"),
    ]

    def setUp(self):
        super().setUp()
        import install
        self.install = importlib.reload(install)

    def test_finds_hand_started_daemons(self):
        found = [pid for pid, _ in self.install.strays(managed_pid=12, table=self.TABLE)]
        self.assertEqual(found, [10, 11])

    def test_ignores_commands_that_merely_name_the_file(self):
        # the first version of this check flagged its own shell heredoc
        found = [pid for pid, _ in self.install.strays(managed_pid=12, table=self.TABLE)]
        for innocent in (20, 21, 22):
            self.assertNotIn(innocent, found)

    def test_excludes_the_managed_daemon(self):
        found = [pid for pid, _ in self.install.strays(managed_pid=10, table=self.TABLE)]
        self.assertNotIn(10, found)

    def test_excludes_itself(self):
        table = [(os.getpid(), "/usr/bin/python3 /repo/nudge_daemon.py")]
        self.assertEqual(self.install.strays(table=table), [])

    def test_status_names_the_stray_and_how_to_stop_it(self):
        self.install._process_table = lambda: [(31337, "/usr/bin/python3 /x/nudge_daemon.py")]
        report = "\n".join(self.install.status_report())
        self.assertIn("stray", report)
        self.assertIn("31337", report)
        self.assertIn("kill 31337", report)

    def test_status_is_quiet_when_nothing_is_hand_started(self):
        self.install._process_table = lambda: []
        self.assertNotIn("stray", "\n".join(self.install.status_report()))


class TestNotifyFallback(unittest.TestCase):
    """Installing terminal-notifier must not silently stop delivery."""

    PRESENT = lambda self, name: "/opt/homebrew/bin/" + name

    class _Result:
        def __init__(self, returncode, stderr=b""):
            self.returncode, self.stderr = returncode, stderr

    def test_prefers_terminal_notifier_when_it_works(self):
        import notify
        calls = []
        argv, _ = notify.send("t", "m", which=self.PRESENT,
                              runner=lambda a, **k: (calls.append(a), self._Result(0))[1])
        self.assertIn("terminal-notifier", argv[0])
        self.assertEqual(len(calls), 1)

    def test_falls_back_when_terminal_notifier_is_not_permitted(self):
        # the real exit 3: "Notifications are not allowed for this application"
        import notify
        results = [self._Result(3, b"Could not request notification permission"),
                   self._Result(0)]
        argv, _ = notify.send("t", "m", which=self.PRESENT,
                              runner=lambda a, **k: results.pop(0))
        self.assertEqual(argv[0], "osascript")

    def test_reports_when_every_sender_fails(self):
        import notify
        argv, attempts = notify.send(
            "t", "m", which=self.PRESENT,
            runner=lambda a, **k: self._Result(3, b"nope"))
        self.assertIsNone(argv)
        self.assertEqual(len(attempts), 2)
        described = notify.describe_failure(attempts)
        self.assertTrue(any("terminal-notifier" in line for line in described))
        self.assertTrue(any("exited 3: nope" in line for line in described))

    def test_osascript_only_when_terminal_notifier_is_absent(self):
        import notify
        forms = notify.commands("t", "m", which=lambda name: None)
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0][0], "osascript")


class TestSound(unittest.TestCase):
    PRESENT = lambda self, name: "/opt/homebrew/bin/" + name

    def test_default_sound_on_both_senders(self):
        import notify
        tn, osa = notify.commands("t", "m", which=self.PRESENT)
        self.assertEqual(tn[-2:], ["-sound", "Ping"])
        self.assertIn("sound name", " ".join(osa))
        self.assertEqual(osa[-1], "Ping")

    def test_sound_is_argv_not_spliced_into_applescript(self):
        import notify
        _, osa = notify.commands("t", "m", which=self.PRESENT, sound='Glass" & (do shell')
        self.assertNotIn("do shell", " ".join(osa[:5]))  # not in the script body
        self.assertEqual(osa[-1], 'Glass" & (do shell')

    def test_silent_omits_the_sound_entirely(self):
        import notify
        tn, osa = notify.commands("t", "m", which=self.PRESENT, sound=None)
        self.assertNotIn("-sound", tn)
        self.assertNotIn("sound name", " ".join(osa))

    def test_env_selects_and_disables(self):
        import notify
        self.assertEqual(notify.sound_name({}), "Ping")
        self.assertEqual(notify.sound_name({"NUDGE_SOUND": "Glass"}), "Glass")
        for off in ("", "none", "OFF", " none "):
            self.assertIsNone(notify.sound_name({"NUDGE_SOUND": off}))


class TestNotifierLookup(unittest.TestCase):
    """launchd hands the daemon a bare PATH; the sender must survive that."""

    def test_pinned_path_wins(self):
        import notify
        found = notify.find_notifier({"NUDGE_NOTIFIER": "/bin/sh"}, which=lambda n: None)
        self.assertEqual(found, "/bin/sh")

    def test_unusable_pin_falls_through_to_osascript(self):
        import notify
        self.assertIsNone(
            notify.find_notifier({"NUDGE_NOTIFIER": "/nope/terminal-notifier"},
                                 which=lambda n: None))

    def test_path_lookup_used_when_nothing_pinned(self):
        import notify
        self.assertEqual(notify.find_notifier({}, which=lambda n: "/somewhere/" + n),
                         "/somewhere/terminal-notifier")

    def test_known_prefixes_searched_when_path_is_bare(self):
        # the actual daemon failure: PATH=/usr/bin:/bin:/usr/sbin:/sbin
        import notify
        real = os.access
        try:
            os.access = lambda p, m: p == "/opt/homebrew/bin/terminal-notifier"
            self.assertEqual(notify.find_notifier({}, which=lambda n: None),
                             "/opt/homebrew/bin/terminal-notifier")
        finally:
            os.access = real


class TestNotifyCommand(unittest.TestCase):
    def test_text_is_argv_never_script_body(self):
        import notify
        argv = notify.command("nudge", 'he said "hi"; rm -rf /\nnext')
        self.assertIn('he said "hi"; rm -rf /\nnext', argv)

    def test_send_uses_injected_runner(self):
        import notify
        calls = []
        notify.send("t", "m", runner=lambda argv, **kw: calls.append(argv))
        self.assertEqual(len(calls), 1)


def read(path):
    with open(path) as f:
        return f.read()


class TestInstall(StoreCase):
    def setUp(self):
        super().setUp()
        import install
        self.install = importlib.reload(install)

    def _sandbox(self):
        """Point every path install writes to at the tmpdir."""
        bin_dir = os.path.join(self.tmp.name, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        self.install.BIN = bin_dir
        self.install.PLIST = os.path.join(self.tmp.name, "agent.plist")
        self.install.SKILL_LINK = os.path.join(self.tmp.name, "skill-link")
        self.install.shim_path = lambda name: os.path.join(bin_dir, name)
        self.install._launchctl = lambda *a: type("R", (), {"returncode": 1,
                                                            "stdout": "", "stderr": ""})()
        self.install._process_table = lambda: []
        return bin_dir

    def test_uninstall_runs_on_a_clean_machine(self):
        # regression: cmd_uninstall referenced an undefined name and raised NameError
        self._sandbox()
        self.assertEqual(self.install.cmd_uninstall(None), 0)

    def test_sibling_clone_is_not_inside_this_one(self):
        # a startswith test would delete /x/nudge-old's skill link from /x/nudge
        root = os.path.join(self.tmp.name, "nudge")
        sibling = os.path.join(self.tmp.name, "nudge-old")
        os.makedirs(os.path.join(root, "inner"))
        os.makedirs(sibling)
        self.assertTrue(self.install._is_inside(os.path.join(root, "inner"), root))
        self.assertFalse(self.install._is_inside(sibling, root))

    def test_failed_removal_does_not_stop_the_rest(self):
        import contextlib, io
        bin_dir = self._sandbox()
        shim = os.path.join(bin_dir, "nudge")
        with open(shim, "w") as f:
            f.write("#!/bin/sh\n# generated by nudge install.py\n")
        with open(self.install.PLIST, "w") as f:
            f.write("<plist/>")
        real_unlink = os.unlink
        def unlink(path):
            if path == self.install.PLIST:
                raise OSError(1, "Operation not permitted")
            return real_unlink(path)
        os.unlink = unlink
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = self.install.cmd_uninstall(None)
        finally:
            os.unlink = real_unlink
        self.assertFalse(os.path.exists(shim))       # kept going
        self.assertIn("FAILED", out.getvalue())
        self.assertEqual(code, 1)                    # and said so

    def test_survivor_makes_uninstall_exit_nonzero(self):
        import contextlib, io
        self._sandbox()
        self.install._process_table = lambda: [(4242, "/usr/bin/python3 /x/nudge_daemon.py")]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = self.install.cmd_uninstall(None)
        self.assertEqual(code, 1)
        self.assertIn("still present", out.getvalue())
        self.assertIn("NOT fully uninstalled", out.getvalue())

    def test_foreign_shim_is_reported_not_silently_skipped(self):
        import contextlib, io
        bin_dir = self._sandbox()
        foreign = os.path.join(bin_dir, "nudge")
        with open(foreign, "w") as f:
            f.write("#!/bin/sh\necho not ours\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.install.cmd_uninstall(None)
        self.assertTrue(os.path.exists(foreign))
        self.assertIn("not written by nudge", out.getvalue())

    def test_uninstall_removes_what_install_wrote(self):
        bin_dir = self._sandbox()
        shim = os.path.join(bin_dir, "nudge")
        with open(shim, "w") as f:
            f.write(self.install.SHIM_MARKER if hasattr(self.install, "SHIM_MARKER") else
                    "#!/bin/sh\n# generated by nudge install.py -- re-run it to repoint, do not edit\n")
        os.chmod(shim, 0o755)
        with open(self.install.PLIST, "w") as f:
            f.write("<plist/>")
        self.assertEqual(self.install.cmd_uninstall(None), 0)
        self.assertFalse(os.path.exists(shim))
        self.assertFalse(os.path.exists(self.install.PLIST))

    def test_uninstall_warns_about_a_surviving_daemon(self):
        import contextlib, io
        self._sandbox()
        self.install._process_table = lambda: [(4242, "/usr/bin/python3 /x/nudge_daemon.py")]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = self.install.cmd_uninstall(None)
        self.assertEqual(code, 1)
        self.assertIn("still running", out.getvalue())

    # --- the LaunchAgent ---

    def test_plist_is_valid_and_keeps_daemon_alive(self):
        import plistlib
        body = self.install.plist_body(here="/proj", home="/h")
        round_tripped = plistlib.loads(plistlib.dumps(body))
        self.assertEqual(round_tripped["Label"], "com.nudge.daemon")
        self.assertEqual(round_tripped["ProgramArguments"],
                         [self.install.shim_path("nudge-daemon")])
        # without both of these a scheduled notification dies with the session
        self.assertTrue(round_tripped["RunAtLoad"])
        self.assertTrue(round_tripped["KeepAlive"])

    def test_plist_paths_are_absolute(self):
        body = self.install.plist_body()
        for key in ("WorkingDirectory", "StandardOutPath", "StandardErrorPath"):
            self.assertTrue(os.path.isabs(body[key]), key)
        self.assertTrue(os.path.isabs(body["ProgramArguments"][0]))

    def test_describe_ignores_the_ppid_line(self):
        out = "\tstate = running\n\tppid = 1\n\tpid = 84930\n"
        self.assertEqual(self.install._describe(out), "pid 84930 (running)")

    def test_describe_without_a_pid(self):
        self.assertEqual(self.install._describe("\tstate = waiting\n"), "no pid (waiting)")

    def test_healthy_is_false_when_the_program_is_gone(self):
        # the moved-clone case: launchd still has the job, the shim does not exist
        plist = os.path.join(self.tmp.name, "agent.plist")
        self.install.PLIST = plist
        import plistlib
        with open(plist, "wb") as f:
            plistlib.dump({"ProgramArguments": [os.path.join(self.tmp.name, "gone")]}, f)
        self.assertEqual(self.install.plist_program(), os.path.join(self.tmp.name, "gone"))
        self.assertFalse(self.install.healthy())

    def test_plist_program_on_a_missing_or_corrupt_plist(self):
        self.install.PLIST = os.path.join(self.tmp.name, "nope.plist")
        self.assertIsNone(self.install.plist_program())
        bad = os.path.join(self.tmp.name, "bad.plist")
        with open(bad, "w") as f:
            f.write("not a plist")
        self.install.PLIST = bad
        self.assertIsNone(self.install.plist_program())

    def test_repair_command_names_this_clone(self):
        self.assertIn(self.install.HERE, self.install.repair_command())
        self.assertIn("install.py install", self.install.repair_command())

    # --- shims ---

    def test_shim_execs_the_clone_it_was_generated_from(self):
        body = self.install.shim_body("/usr/bin/python3", "/clone/nudge.py")
        self.assertTrue(body.startswith("#!/bin/sh\n"))
        self.assertIn("exec '/usr/bin/python3' '/clone/nudge.py' \"$@\"", body)

    def test_shim_quotes_a_path_with_spaces(self):
        body = self.install.shim_body("/usr/bin/python3", "/my clone/nudge.py")
        self.assertIn("'/my clone/nudge.py'", body)

    def test_write_shims_are_executable_and_point_at_this_clone(self):
        bindir = os.path.join(self.tmp.name, "bin")
        written = self.install.write_shims(python="/py", here="/clone", bindir=bindir)
        self.assertEqual(sorted(os.path.basename(p) for p in written),
                         ["nudge", "nudge-daemon"])
        for path in written:
            self.assertTrue(os.access(path, os.X_OK), path)
        self.assertIn("/clone/nudge.py", read(os.path.join(bindir, "nudge")))
        self.assertIn("/clone/nudge_daemon.py", read(os.path.join(bindir, "nudge-daemon")))

    def test_write_shims_repoints_a_moved_clone(self):
        bindir = os.path.join(self.tmp.name, "bin")
        self.install.write_shims(python="/py", here="/old", bindir=bindir)
        self.install.write_shims(python="/py", here="/new", bindir=bindir)
        body = read(os.path.join(bindir, "nudge"))
        self.assertIn("/new/nudge.py", body)
        self.assertNotIn("/old/nudge.py", body)

    def test_write_shims_refuses_to_clobber_a_foreign_command(self):
        bindir = os.path.join(self.tmp.name, "bin")
        os.makedirs(bindir)
        someone_elses = os.path.join(bindir, "nudge")
        with open(someone_elses, "w") as f:
            f.write("#!/bin/sh\necho not ours\n")
        with self.assertRaises(SystemExit):
            self.install.write_shims(python="/py", here="/clone", bindir=bindir)
        with open(someone_elses) as f:
            self.assertEqual(f.read(), "#!/bin/sh\necho not ours\n")

    def test_write_shims_writes_both_or_neither(self):
        # a foreign nudge-daemon must not leave a half-installed nudge behind
        bindir = os.path.join(self.tmp.name, "bin")
        os.makedirs(bindir)
        with open(os.path.join(bindir, "nudge-daemon"), "w") as f:
            f.write("#!/bin/sh\necho not ours\n")
        with self.assertRaises(SystemExit):
            self.install.write_shims(python="/py", here="/clone", bindir=bindir)
        self.assertFalse(os.path.exists(os.path.join(bindir, "nudge")))

    def test_is_ours_distinguishes_generated_shims(self):
        bindir = os.path.join(self.tmp.name, "bin")
        self.install.write_shims(python="/py", here="/clone", bindir=bindir)
        self.assertTrue(self.install.is_ours(os.path.join(bindir, "nudge")))
        foreign = os.path.join(bindir, "other")
        with open(foreign, "w") as f:
            f.write("#!/bin/sh\necho hi\n")
        self.assertFalse(self.install.is_ours(foreign))

    def test_is_ours_on_a_missing_or_binary_file(self):
        self.assertFalse(self.install.is_ours(os.path.join(self.tmp.name, "nope")))
        blob = os.path.join(self.tmp.name, "blob")
        with open(blob, "wb") as f:
            f.write(b"\x00\x01\x02\xff")
        self.assertFalse(self.install.is_ours(blob))

    def test_shim_target_reads_back_the_script(self):
        bindir = os.path.join(self.tmp.name, "bin")
        self.install.write_shims(python="/py", here="/clone", bindir=bindir)
        self.assertEqual(self.install._shim_target(os.path.join(bindir, "nudge")),
                         "/clone/nudge.py")

    # --- the skill link ---

    def test_link_skill_creates_then_is_idempotent(self):
        link = os.path.join(self.tmp.name, "nudge")
        target = os.path.join(self.tmp.name, "skill")
        os.makedirs(target)
        self.assertEqual(self.install.link_skill(link, target), "linked")
        self.assertEqual(self.install.link_skill(link, target), "already linked")
        self.assertEqual(os.path.realpath(link), os.path.realpath(target))

    def test_link_skill_repoints_a_moved_clone(self):
        link = os.path.join(self.tmp.name, "nudge")
        old = os.path.join(self.tmp.name, "old")
        new = os.path.join(self.tmp.name, "new")
        os.makedirs(old)
        os.makedirs(new)
        self.install.link_skill(link, old)
        self.assertEqual(self.install.link_skill(link, new), "repointed")
        self.assertEqual(os.path.realpath(link), os.path.realpath(new))

    def test_link_skill_never_clobbers_a_real_directory(self):
        link = os.path.join(self.tmp.name, "nudge")
        target = os.path.join(self.tmp.name, "skill")
        os.makedirs(target)
        os.makedirs(link)
        with open(os.path.join(link, "SKILL.md"), "w") as f:
            f.write("someone else's skill")
        result = self.install.link_skill(link, target)
        self.assertIn("left alone", result)
        self.assertFalse(os.path.islink(link))
        self.assertEqual(read(os.path.join(link, "SKILL.md")), "someone else's skill")


if __name__ == "__main__":
    unittest.main(verbosity=2)
