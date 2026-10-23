"""Runs server/wsl/swg-offline-server for real, with mysql/service stubbed and a fake core3."""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "server" / "wsl" / "swg-offline-server"
FAKE_CORE3 = Path(__file__).with_name("fake_core3.py")


def write_exe(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("setpriv"), "needs Linux setpriv")
class ServerScriptTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.bin = self.root / "bin"
        (self.bin / "conf").mkdir(parents=True)
        (self.bin / "scripts" / "managers").mkdir(parents=True)
        (self.bin / "scripts" / "managers" / "loot_manager-local.lua").write_text("stale = 1\n")
        stubs = self.root / "stubs"
        stubs.mkdir()
        self.calls = self.root / "calls.log"
        for name in ("mysql", "mysqladmin", "service"):
            write_exe(stubs / name, f'#!/bin/sh\necho "{name} $*" >> "{self.calls}"\n')
        write_exe(self.root / "core3", f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_CORE3}"\n')
        self.overrides = self.root / "overrides"
        self.overrides.mkdir()
        (self.overrides / "config-offline.lua").write_bytes(b'ZonesEnabled = { "naboo" }\r\n')
        (self.overrides / "player_manager-local.lua").write_text("globalExpMultiplier = 4.0\n")
        user = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
        conf = self.root / "swg-offline.conf"
        conf.write_text(f"RUN_USER='{user}'\nCORE3_BIN='{self.bin}'\nCORE3_EXE='{self.root / 'core3'}'\n"
                        f"MYSQL_DEFAULTS='{self.root / 'my.cnf'}'\n")
        self.commands = self.root / "commands.log"
        self.env = dict(os.environ, PATH=f"{stubs}:{os.environ['PATH']}", SWG_OFFLINE_CONF=str(conf),
                        FAKE_CORE3_LOG=str(self.commands))

    def run_script(self, *args, stdin=""):
        return subprocess.run(["bash", str(SCRIPT), *args], input=stdin, capture_output=True, text=True,
                              env=self.env, timeout=60)

    def test_session(self):
        out = self.run_script("--address", "172.20.1.2", "--overrides", str(self.overrides),
                              "--admin-user", "player", "--admin-level", "15", stdin="save\n")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("READY", out.stdout)
        # stdin EOF turns into a clean exit after the commands that were sent
        self.assertEqual(self.commands.read_text().split(), ["save", "exit"])
        calls = self.calls.read_text()
        self.assertIn("UPDATE galaxy SET address = '172.20.1.2';", calls)
        self.assertIn("ALTER TABLE accounts ALTER admin_level SET DEFAULT 15;", calls)
        self.assertIn("WHERE username = 'player';", calls)
        self.assertIn("service mariadb stop", calls)
        self.assertEqual((self.bin / "conf" / "config-offline.lua").read_bytes(), b'ZonesEnabled = { "naboo" }\n')
        self.assertTrue((self.bin / "scripts" / "managers" / "player_manager-local.lua").exists())
        self.assertFalse((self.bin / "scripts" / "managers" / "loot_manager-local.lua").exists())

    def test_core3_lingering_after_close_is_stopped_as_success(self):
        self.env["FAKE_CORE3_HANG"] = "1"
        out = self.run_script("--address", "127.0.0.1", stdin="")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("server closed", out.stdout)
        self.assertIn("did not exit, stopping it", out.stderr)
        self.assertIn("service mariadb stop", self.calls.read_text())

    def test_rejects_bad_input(self):
        self.assertEqual(self.run_script("--address", "1.2.3.4; rm -rf /").returncode, 11)
        out = self.run_script("--address", "1.2.3.4", "--admin-user", "x' OR '1'='1")
        self.assertEqual(out.returncode, 11)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
