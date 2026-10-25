import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from swg_offline import client
from swg_offline.session import Session, Stage
from swg_offline.settings import Settings

FAKE_CORE3 = [sys.executable, str(Path(__file__).with_name("fake_core3.py"))]


def make_swg_dir(root: Path) -> Path:
    swg = root / "SWG"
    swg.mkdir()
    (swg / "SWGEmu.exe").touch()
    for tre in client.REQUIRED_TRES:
        (swg / tre).touch()
    (swg / client.LOGIN_CFG).write_text("[ClientGame]\n\tloginServerAddress0=login.swgemu.com\n")
    return swg


class FakeClient:
    """Plays for a moment, checking the login config points at the local server meanwhile."""

    def __init__(self, seen):
        self.seen = seen

    def __call__(self, swg_dir, exe):
        self.seen.append((swg_dir / client.LOGIN_CFG).read_text())
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.3)"])
        return self.proc


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.swg = make_swg_dir(self.root)
        self.home = self.root / "home"
        self.commands = self.root / "commands.log"
        env = mock.patch.dict(os.environ, {"FAKE_CORE3_LOG": str(self.commands)})
        env.start()
        self.addCleanup(env.stop)
        self.statuses = []
        self.cfg_seen = []

    def session(self, **settings):
        s = Settings(swg_dir=str(self.swg), address="10.1.2.3", boot_timeout_seconds=20,
                     shutdown_timeout_seconds=20, **settings)
        return Session(s, lambda stage, text: self.statuses.append((stage, text)), server_args=FAKE_CORE3,
                       start_client=FakeClient(self.cfg_seen), home=self.home)

    def stages(self):
        out = []
        for stage, _ in self.statuses:
            if not out or out[-1] != stage:
                out.append(stage)
        return out

    def test_full_session_saves_and_restores_config(self):
        self.session(preset="tuned-solo").run()
        self.assertEqual(self.stages(), [Stage.CHECKING, Stage.BOOTING, Stage.PLAYING, Stage.SAVING, Stage.DONE])
        self.assertEqual(self.commands.read_text().split(), ["save", "exit"])
        self.assertIn("loginServerAddress0=10.1.2.3", self.cfg_seen[0])
        self.assertIn("login.swgemu.com", (self.swg / client.LOGIN_CFG).read_text())
        self.assertIn("globalExpMultiplier = 4.0",
                      (self.home / "overrides" / "player_manager-local.lua").read_text())
        self.assertIn("READY", (self.home / "logs" / "server.log").read_text())

    def test_server_that_lingers_after_closing_is_stopped_as_saved(self):
        with mock.patch.dict(os.environ, {"FAKE_CORE3_HANG": "1"}):
            started = time.monotonic()
            self.session().run()
        self.assertEqual(self.statuses[-1][0], Stage.DONE, self.statuses[-1])
        self.assertLess(time.monotonic() - started, 15)

    def test_boot_failure_reports_server_output(self):
        with mock.patch.dict(os.environ, {"FAKE_CORE3_FAIL": "1"}):
            self.session().run()
        stage, text = self.statuses[-1]
        self.assertEqual(stage, Stage.FAILED)
        self.assertIn("could not open tre files", text)
        self.assertEqual(self.cfg_seen, [])

    def test_missing_tres_fail_before_starting_server(self):
        (self.swg / "bottom.tre").unlink()
        self.session().run()
        self.assertEqual(self.stages(), [Stage.CHECKING, Stage.FAILED])
        self.assertFalse(self.commands.exists())

    def test_unwritable_swg_folder_fails_before_starting_server(self):
        with mock.patch.object(client, "is_writable", return_value=False), \
                mock.patch.object(client, "virtual_store_dir", return_value=None):
            self.session().run()
        self.assertEqual(self.stages(), [Stage.CHECKING, Stage.FAILED])
        self.assertIn("can't write to your SWG folder", self.statuses[-1][1])
        self.assertFalse(self.commands.exists())

    def test_cancel_while_playing_still_saves(self):
        s = self.session()
        s._start_client = lambda d, e: subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        t = threading.Thread(target=s.run)
        t.start()
        while not any(stage == Stage.PLAYING for stage, _ in self.statuses):
            t.join(0.05)
        s.cancel()
        t.join(20)
        s.client.kill()
        s.client.wait()
        self.assertEqual(self.statuses[-1][0], Stage.DONE)
        self.assertEqual(self.commands.read_text().split(), ["save", "exit"])


if __name__ == "__main__":
    unittest.main()
