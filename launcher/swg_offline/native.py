"""Running the server natively on Windows: core3.exe on SQLite, as the installer lays it out.

The server folder is Core3's bin/ (conf/, scripts/, databases/...) with core3.exe and its DLLs.
Nothing is copied from the SWG folder: TrePath points straight at it.
"""

import contextlib
import shutil
import sqlite3
import sys
from pathlib import Path, PureWindowsPath
from typing import List

from . import presets
from .settings import ACCOUNT_NAME, Settings

SERVER_EXE = "core3.exe"
DB_PATH = "databases/swgemu.sqlite3"
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
    """Puts the rendered preset files and config-local.lua where core3.exe reads them."""
    (server_dir / "conf" / "config-local.lua").write_text(local_config(settings), encoding="utf-8", newline="\n")
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
