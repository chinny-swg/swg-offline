import contextlib
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from swg_offline import native, presets
from swg_offline.session import Session, Stage
from swg_offline.settings import Settings
from tests.test_session import FAKE_CORE3, FakeClient, make_swg_dir


def make_server_dir(root: Path) -> Path:
    server = root / "server"
    (server / "conf").mkdir(parents=True)
    (server / "scripts" / "managers").mkdir(parents=True)
    (server / "conf" / "config.lua").write_text("Core3 = {}\n")
    (server / native.SERVER_EXE).touch()
    return server


def connect(db: Path):
    """Commits and closes (Windows cannot delete an open database file)."""
    con = sqlite3.connect(str(db))
    return contextlib.closing(con), con


def execute(db: Path, sql: str):
    closer, con = connect(db)
    with closer, con:
        return con.execute(sql).fetchall()


def accounts(db: Path):
    return execute(db, "SELECT username, admin_level FROM accounts ORDER BY account_id")


class NativeTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def test_local_config(self):
        text = native.local_config(Settings(swg_dir=r"C:\Games\SWG Emu"))
        self.assertIn('DBType = "sqlite"', text)
        self.assertIn('TrePath = "C:/Games/SWG Emu"', text)
        self.assertIn("ShutdownOnConsoleEOF = 1", text)
        self.assertIn('loadfile("conf/config-offline.lua")', text)

    def test_backend_auto_detects_server(self):
        s = Settings(server_dir=str(self.root / "server"))
        self.assertEqual(s.resolved_backend(), "wsl")
        make_server_dir(self.root)
        self.assertEqual(s.resolved_backend(), "native")
        self.assertEqual(Settings(backend="wsl", server_dir=s.server_dir).resolved_backend(), "wsl")

    def test_apply_admin_existing_and_future_accounts(self):
        db = self.root / "swgemu.sqlite3"
        execute(db, "CREATE TABLE accounts (account_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    " username TEXT NOT NULL, admin_level INTEGER NOT NULL DEFAULT 0)")
        execute(db, "INSERT INTO accounts (username) VALUES ('player')")
        native.apply_admin(db, "player", 15)
        execute(db, "INSERT INTO accounts (username) VALUES ('other')")
        native.apply_admin(db, "newbie", 15)  # moves the trigger to the new name
        execute(db, "INSERT INTO accounts (username) VALUES ('newbie')")
        self.assertEqual(accounts(db), [("player", 15), ("other", 0), ("newbie", 15)])
        native.apply_admin(db, "newbie", 0)
        execute(db, "INSERT INTO accounts (username) VALUES ('newbie')")
        self.assertEqual(accounts(db)[-2:], [("newbie", 0), ("newbie", 0)])

    def test_parse_tasklist(self):
        out = '"core3.exe","5024","Console","1","3,145,728 K"\r\n"Core3.EXE","77","Console","1","10 K"\r\n'
        self.assertEqual(native.parse_tasklist(out), [5024, 77])
        self.assertEqual(native.parse_tasklist("INFO: No tasks are running which match the specified criteria."), [])

    def test_port_in_use(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as held:
            held.bind(("127.0.0.1", 0))
            port = held.getsockname()[1]
            self.assertTrue(native.port_in_use("127.0.0.1", port))
        self.assertFalse(native.port_in_use("127.0.0.1", port))

    def native_session(self, statuses, **settings):
        swg = make_swg_dir(self.root)
        server = make_server_dir(self.root)
        s = Settings(swg_dir=str(swg), server_dir=str(server), backend="native",
                     boot_timeout_seconds=20, shutdown_timeout_seconds=20, **settings)
        return Session(s, lambda st, t: statuses.append((st, t)), server_args=FAKE_CORE3,
                       start_client=FakeClient([]), home=self.root / "home")

    def test_leftover_server_fails_before_starting_another(self):
        statuses = []
        with mock.patch.object(native, "running_servers", return_value=[5024]):
            self.native_session(statuses).run()
        self.assertEqual([st for st, _ in statuses], [Stage.CHECKING, Stage.FAILED])
        self.assertIn("PID 5024", statuses[-1][1])
        self.assertFalse((self.root / "server" / "conf" / "config-local.lua").exists())

    def test_busy_login_port_fails_before_starting_server(self):
        statuses = []
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as held:
            held.bind(("127.0.0.1", 0))
            self.native_session(statuses, login_port=held.getsockname()[1]).run()
        self.assertEqual([st for st, _ in statuses], [Stage.CHECKING, Stage.FAILED])
        self.assertIn("already using the login port", statuses[-1][1])

    def test_install_json_supplies_swg_dir(self):
        app = self.root / "app"
        (app / "server").mkdir(parents=True)
        (app / "install.json").write_text('{"swg_dir": "C:\\\\SWGEmu"}')
        with mock.patch("swg_offline.native.default_server_dir", return_value=str(app / "server")):
            self.assertEqual(Settings.load(self.root / "missing.json").swg_dir, "C:\\SWGEmu")
            (self.root / "s.json").write_text('{"swg_dir": "D:\\\\Mine"}')
            self.assertEqual(Settings.load(self.root / "s.json").swg_dir, "D:\\Mine")

    def test_apply_admin_rejects_injection(self):
        with self.assertRaises(ValueError):
            native.apply_admin(self.root / "x.db", "a'; DROP TABLE accounts; --", 15)

    def test_session_installs_config_and_applies_sandbox_admin(self):
        swg = make_swg_dir(self.root)
        server = make_server_dir(self.root)
        db = server / native.DB_PATH
        statuses, seen = [], []
        settings = Settings(swg_dir=str(swg), server_dir=str(server), backend="native", preset="sandbox",
                            boot_timeout_seconds=20, shutdown_timeout_seconds=20)
        with mock.patch.dict(os.environ, {"FAKE_CORE3_SQLITE": str(db)}):
            # The real command is core3.exe; the fake runs in the same working directory
            Session(settings, lambda st, t: statuses.append((st, t)), server_args=FAKE_CORE3,
                    start_client=FakeClient(seen), home=self.root / "home").run()
        self.assertEqual(statuses[-1][0], Stage.DONE, statuses[-1])
        self.assertIn("bind=127.0.0.1", (self.root / "home" / "logs" / "server.log").read_text())
        self.assertIn("loginServerAddress0=127.0.0.1", seen[0])
        self.assertIn('DBType = "sqlite"', (server / "conf" / "config-local.lua").read_text())
        self.assertTrue((server / "conf" / "config-offline.lua").exists())
        self.assertIn("set_lg_regionmax 16777216", (server / "databases" / "DB_CONFIG").read_text())
        self.assertTrue((server / "scripts" / "managers" / "player_manager-local.lua").exists())
        execute(db, "INSERT INTO accounts (username) VALUES ('player')")
        self.assertEqual(accounts(db), [("player", presets.ADMIN_LEVEL)])


if __name__ == "__main__":
    unittest.main()
