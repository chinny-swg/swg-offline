import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_crashed_session_created_file_is_removed(self):
        login = client.LoginConfig(self.dir)
        login.apply("127.0.0.1", 44453)  # no restore: the launcher crashed
        again = client.LoginConfig(self.dir)
        again.apply("127.0.0.1", 44453)
        again.restore()
        self.assertFalse(self.cfg.exists())
        self.assertFalse(login.marker.exists())

    def test_restore_without_apply_leaves_player_file(self):
        self.cfg.write_text("mine")
        client.LoginConfig(self.dir).restore()
        self.assertEqual(self.cfg.read_text(), "mine")


def fake_exe(machine: int, manifest: bool = False) -> bytes:
    """Just enough of a PE file for is_virtualized_exe: DOS header, PE signature, machine."""
    data = bytearray(b"MZ" + b"\0" * 0x3A + struct.pack("<I", 0x40))
    data += b"PE\0\0" + struct.pack("<H", machine) + b"\0" * 32
    if manifest:
        data += b'<requestedExecutionLevel level="asInvoker" uiAccess="false"/>'
    return bytes(data)


WINDOWS_ENV = {
    "LOCALAPPDATA": "/home/u/AppData/Local",
    "ProgramFiles": "C:\\Program Files",
    "ProgramFiles(x86)": "C:\\Program Files (x86)",
}


class VirtualStoreTest(unittest.TestCase):
    def test_program_files_maps_into_virtual_store(self):
        got = client.virtual_store_dir(Path("C:\\Program Files (x86)\\SWGEmu\\SWGEmu"), WINDOWS_ENV)
        self.assertEqual(got, Path("/home/u/AppData/Local", "VirtualStore", "Program Files (x86)", "SWGEmu", "SWGEmu"))

    def test_case_is_ignored(self):
        got = client.virtual_store_dir(Path("c:\\program files (x86)\\SWGEmu"), WINDOWS_ENV)
        self.assertEqual(got, Path("/home/u/AppData/Local", "VirtualStore", "program files (x86)", "SWGEmu"))

    def test_other_folders_are_not_virtualized(self):
        self.assertIsNone(client.virtual_store_dir(Path("C:\\SWGEmu"), WINDOWS_ENV))
        self.assertIsNone(client.virtual_store_dir(Path("D:\\Program Files (x86)\\SWGEmu"), WINDOWS_ENV))
        self.assertIsNone(client.virtual_store_dir(Path("C:\\Program Files Extra\\SWGEmu"), WINDOWS_ENV))

    def test_only_32_bit_exes_without_manifest_are_virtualized(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        exe = d / "SWGEmu.exe"
        exe.write_bytes(fake_exe(0x14C))
        self.assertTrue(client.is_virtualized_exe(exe))
        exe.write_bytes(fake_exe(0x14C, manifest=True))
        self.assertFalse(client.is_virtualized_exe(exe))
        exe.write_bytes(fake_exe(0x8664))
        self.assertFalse(client.is_virtualized_exe(exe))
        exe.write_bytes(b"not an exe")
        self.assertFalse(client.is_virtualized_exe(exe))
        self.assertFalse(client.is_virtualized_exe(d / "missing.exe"))


class ProtectedFolderTest(unittest.TestCase):
    """The SWG folder is read-only (Program Files): the config goes to the VirtualStore."""

    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        self.swg = root / "SWGEmu"
        self.swg.mkdir()
        self.virtual = root / "VirtualStore" / "SWGEmu"
        (self.swg / client.LOGIN_CFG).write_bytes(LIVE_CFG.encode())
        (self.swg / "SWGEmu.exe").write_bytes(fake_exe(0x14C))
        for target, value in (("is_writable", False), ("virtual_store_dir", self.virtual)):
            patcher = mock.patch.object(client, target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_session_copy_goes_to_virtual_store_and_is_removed(self):
        login = client.LoginConfig(self.swg)
        login.prepare()
        login.apply("127.0.0.1", 44453)
        virtual_cfg = self.virtual / client.LOGIN_CFG
        text = virtual_cfg.read_bytes()
        self.assertIn(b"loginServerAddress0=127.0.0.1\r\n", text)
        self.assertIn(b"foo=1", text)  # built from the player's real file
        login.restore()
        self.assertFalse(virtual_cfg.exists())
        self.assertEqual(list(self.virtual.iterdir()), [])
        self.assertEqual((self.swg / client.LOGIN_CFG).read_bytes(), LIVE_CFG.encode())

    def test_existing_virtual_copy_is_put_back(self):
        self.virtual.mkdir(parents=True)
        (self.virtual / client.LOGIN_CFG).write_text("[ClientGame]\n\tloginServerAddress0=my.server\n")
        login = client.LoginConfig(self.swg)
        login.prepare()
        login.apply("127.0.0.1", 44453)
        login.restore()
        self.assertIn("my.server", (self.virtual / client.LOGIN_CFG).read_text())

    def test_crashed_session_copy_is_not_kept(self):
        login = client.LoginConfig(self.swg)
        login.prepare()
        login.apply("127.0.0.1", 44453)  # no restore: the launcher crashed
        again = client.LoginConfig(self.swg)
        again.prepare()
        again.apply("127.0.0.1", 44453)
        again.restore()
        self.assertFalse((self.virtual / client.LOGIN_CFG).exists())

    def test_client_that_is_not_virtualized_is_reported(self):
        (self.swg / "SWGEmu.exe").write_bytes(fake_exe(0x14C, manifest=True))
        with self.assertRaises(client.LoginConfigError) as e:
            client.LoginConfig(self.swg).prepare()
        self.assertIn("C:\\SWGEmu", str(e.exception))


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
