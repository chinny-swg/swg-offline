"""Running the server natively on Windows: core3.exe on SQLite, as the installer lays it out.

The server folder is Core3's bin/ (conf/, scripts/, databases/...) with core3.exe and its DLLs.
Nothing is copied from the SWG folder: TrePath points straight at it.
"""

import contextlib
import csv
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from typing import List

from . import presets
from .settings import ACCOUNT_NAME, Settings

SERVER_EXE = "core3.exe"
DB_PATH = "databases/swgemu.sqlite3"

# Berkeley DB reads DB_CONFIG from its environment folder (Core3's databases/) when it opens it.
# The Windows build links vcpkg's Berkeley DB 4.8, whose log region has a fixed size; Core3 opens
# one handle per database per thread, and registering them all overflowed the default during the
# first full save ("Logging region out of memory", then ENOMEM, "Not enough space", opening a db).
# Core3 opens the environment with DB_RECOVER, which rebuilds the region at this size every start.
DB_CONFIG = """# Written by SWG Offline on every start; edits are overwritten.
set_lg_regionmax 16777216
"""
ADMIN_TRIGGER = "swg_offline_admin"


def default_server_dir() -> str:
    """The installer puts the server in 'server' next to SWGOffline.exe."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    return str(base / "server")


def check_server(server_dir: Path) -> List[str]:
    if not (server_dir / SERVER_EXE).is_file():
        return [f"{SERVER_EXE} not found in {server_dir}"]
    if not (server_dir / "conf" / "config.lua").is_file():
        return [f"{server_dir} is missing conf/config.lua"]
    return []


def parse_tasklist(output: str) -> List[int]:
    """PIDs from `tasklist /FO CSV /NH` output ("INFO: No tasks..." when there are none)."""
    pids = []
    for row in csv.reader(output.splitlines()):
        if len(row) >= 2 and row[0].lower() == SERVER_EXE and row[1].isdigit():
            pids.append(int(row[1]))
    return pids


def running_servers() -> List[int]:
    """PIDs of core3.exe processes, e.g. one left from a session whose save failed."""
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {SERVER_EXE}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_tasklist(out)


def port_in_use(address: str, port: int) -> bool:
    """True when something already holds the UDP login port (SWG's protocol is UDP)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.bind((address, port))
        except OSError:
            return True
    return False


def check_not_running(address: str, port: int) -> List[str]:
    """A server that is still up (saving, or stuck after a failed save) would hold the database and
    the login port, and the new one could not start."""
    pids = running_servers()
    if pids:
        return [f"An SWG Offline server is still running ({SERVER_EXE}, PID "
                f"{', '.join(map(str, pids))}), probably left over from your last session. Wait a "
                f"minute in case it is still saving, or end {SERVER_EXE} in Task Manager (Details "
                "tab), then press Play again."]
    if port_in_use(address, port):
        return [f"Something on this PC is already using the login port ({address}:{port}). If it "
                f"is {SERVER_EXE}, end it in Task Manager (Details tab), then press Play again."]
    return []


def lua_path(path: str) -> str:
    r"""C:\Games\SWG -> C:/Games/SWG, which Core3's file code opens on Windows too."""
    return PureWindowsPath(path).as_posix()


def local_config(settings: Settings) -> str:
    values = {
        "DBType": "sqlite",
        "DBPath": DB_PATH,
        "TrePath": lua_path(settings.swg_dir),
        "MantisHost": "",
        "ShutdownOnConsoleEOF": 1,
        "ProgressMonitors": "false",
    }
    text = presets.lua_file("Native offline server", values)
    return text + '''
local offlineConfig = loadfile("conf/config-offline.lua")

if offlineConfig ~= nil then
	offlineConfig()
end
'''


def install(server_dir: Path, overrides_dir: Path, settings: Settings) -> None:
    """Puts the rendered preset files, config-local.lua and DB_CONFIG where core3.exe reads them."""
    (server_dir / "conf" / "config-local.lua").write_text(local_config(settings), encoding="utf-8", newline="\n")
    databases = server_dir / "databases"
    databases.mkdir(exist_ok=True)
    (databases / "DB_CONFIG").write_text(DB_CONFIG, encoding="ascii", newline="\n")
    shutil.copyfile(overrides_dir / "config-offline.lua", server_dir / "conf" / "config-offline.lua")
    for name in ("player_manager-local.lua", "loot_manager-local.lua"):
        shutil.copyfile(overrides_dir / name, server_dir / "scripts" / "managers" / name)


def apply_admin(db_path: Path, account: str, level: int) -> None:
    """Sets the account's admin level, including when AutoReg creates it later this session."""
    if not ACCOUNT_NAME.match(account):
        raise ValueError(f"invalid account name {account!r}")
    if not db_path.exists():
        return
    with contextlib.closing(sqlite3.connect(str(db_path), timeout=30)) as db, db:
        db.execute("UPDATE accounts SET admin_level = ? WHERE username = ?", (level, account))
        db.execute(f"DROP TRIGGER IF EXISTS {ADMIN_TRIGGER}")
        if level > 0:
            # Triggers take no parameters; the name is checked against ACCOUNT_NAME above
            db.execute(f"CREATE TRIGGER {ADMIN_TRIGGER} AFTER INSERT ON accounts "
                       f"WHEN NEW.username = '{account}' BEGIN "
                       f"UPDATE accounts SET admin_level = {int(level)} WHERE account_id = NEW.account_id; END")
