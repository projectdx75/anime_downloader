import subprocess
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zendriver_cleanup


class ZendriverCleanupTests(unittest.TestCase):
    def test_find_port_pids_falls_back_to_ss_when_lsof_missing(self):
        calls = []

        def fake_which(cmd):
            return None if cmd == "lsof" else f"/usr/bin/{cmd}"

        def fake_runner(cmd, capture_output, text, timeout, check=False):
            calls.append(cmd)
            if cmd[0] == "ss":
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout="LISTEN 0 128 127.0.0.1:19876 0.0.0.0:* users:((\"python3\",pid=111,fd=3),(\"python3\",pid=222,fd=5))\n",
                    stderr="",
                )
            raise AssertionError(f"unexpected command: {cmd}")

        pids = zendriver_cleanup.find_port_pids(
            19876,
            runner=fake_runner,
            which=fake_which,
        )

        self.assertEqual(pids, [111, 222])
        self.assertEqual(calls, [["ss", "-ltnp"]])

    def test_find_stale_browser_pids_matches_only_zendriver_profiles(self):
        def fake_runner(cmd, capture_output, text, timeout, check=False):
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=(
                    "100 /proc/self/exe --type=utility --user-data-dir=/tmp/zd_daemon_0_1_google-chrome\n"
                    "101 /usr/bin/google-chrome --user-data-dir=/tmp/other_profile\n"
                    "102 /usr/bin/chromium --user-data-dir=/tmp/zd_daemon_0_2_chromium\n"
                    "103 python some_script.py\n"
                ),
                stderr="",
            )

        pids = zendriver_cleanup.find_stale_browser_pids(runner=fake_runner)

        self.assertEqual(pids, [100, 102])


if __name__ == "__main__":
    unittest.main()
