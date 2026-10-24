import shutil
import tempfile
import unittest
from pathlib import Path

from swg_offline import client

LIVE_CFG = "[ClientGame]\r\n\tloginServerAddress0=login.swgemu.com\r\n\tloginServerPort0=44453\r\n\tfoo=1\r\n"


class SetLoginServerTest(unittest.TestCase):
    def test_replaces_existing_values_and_keeps_others(self):
        out = client.set_login_server(LIVE_CFG, "172.20.1.2", 44453)
        self.assertIn("\tloginServerAddress0=172.20.1.2", out)
        self.assertIn("\tloginServerPort0=44453", out)
        self.assertIn("\tfoo=1", out)
        self.assertNotIn("swgemu.com", out)

    def test_adds_missing_keys_under_clientgame(self):
        out = client.set_login_server("[Other]\nx=1\n[ClientGame]\nbar=2\n", "127.0.0.1", 44453)
        lines = out.splitlines()
        i = lines.index("[ClientGame]")
        self.assertEqual(lines[i + 1:i + 3], ["\tloginServerAddress0=127.0.0.1", "\tloginServerPort0=44453"])
        self.assertIn("x=1", lines)

    def test_empty_file(self):
        out = client.set_login_server("", "127.0.0.1", 44453)
        self.assertEqual(out.splitlines()[0], "[ClientGame]")


class LoginConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.cfg = self.dir / client.LOGIN_CFG

    def test_apply_then_restore_puts_original_back(self):
        self.cfg.write_bytes(LIVE_CFG.encode())
        login = client.LoginConfig(self.dir)
        login.apply("127.0.0.1", 44453)
        self.assertIn(b"loginServerAddress0=127.0.0.1\r\n", self.cfg.read_bytes())
        login.restore()
        self.assertEqual(self.cfg.read_bytes(), LIVE_CFG.encode())
        self.assertFalse(login.backup.exists())

    def test_crashed_session_backup_is_kept_as_original(self):
        login = client.LoginConfig(self.dir)
        login.backup.write_bytes(LIVE_CFG.encode())
        self.cfg.write_text("[ClientGame]\nloginServerAddress0=127.0.0.1\n")
        login.apply("10.0.0.5", 44453)
        login.restore()
        self.assertEqual(self.cfg.read_bytes(), LIVE_CFG.encode())

    def test_created_file_is_removed(self):
        login = client.LoginConfig(self.dir)
        login.apply("127.0.0.1", 44453)
        self.assertTrue(self.cfg.exists())
        login.restore()
        self.assertFalse(self.cfg.exists())

    def test_restore_without_apply_leaves_player_file(self):
        self.cfg.write_text("mine")
        client.LoginConfig(self.dir).restore()
        self.assertEqual(self.cfg.read_text(), "mine")


class CheckInstallTest(unittest.TestCase):
    def test_reports_missing_pieces(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        problems = client.check_install(d, "SWGEmu.exe")
        self.assertEqual(len(problems), 2)
        (d / "SWGEmu.exe").touch()
        for tre in client.REQUIRED_TRES:
            (d / tre).touch()
        self.assertEqual(client.check_install(d, "SWGEmu.exe"), [])

    def test_tre_list_matches_core3_count(self):
        self.assertEqual(len(set(client.REQUIRED_TRES)), 51)


if __name__ == "__main__":
    unittest.main()
