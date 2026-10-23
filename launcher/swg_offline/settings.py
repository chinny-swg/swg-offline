"""Launcher settings, stored as JSON in the user's app-data folder."""

import dataclasses
import json
import os
import re
from pathlib import Path
from typing import List

ZONE_NAME = re.compile(r"^[a-z0-9_]+$")
ACCOUNT_NAME = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

ALL_GROUND_ZONES = [
    "corellia", "dantooine", "dathomir", "dungeon1", "endor", "lok",
    "naboo", "rori", "talus", "tatooine", "tutorial", "yavin4",
]


def data_dir() -> Path:
    """Where settings, logs and rendered overrides live (%LOCALAPPDATA%\\SWGOffline on Windows)."""
    base = os.environ.get("SWG_OFFLINE_HOME")
    if base:
        return Path(base)
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "SWGOffline"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "swg-offline"


@dataclasses.dataclass
class Settings:
    # Folder of the player's own SWGEmu-patched 14.1 client (holds SWGEmu.exe and the TREs)
    swg_dir: str = ""
    client_exe: str = "SWGEmu.exe"
    preset: str = "faithful"
    # Account name used at the client's login screen; AutoReg creates it on first login.
    # The Sandbox preset gives this account admin rights.
    account: str = "player"
    wsl_distro: str = "Debian"
    # "auto" uses 127.0.0.1 with WSL mirrored networking, else the WSL VM's own address
    address: str = "auto"
    login_port: int = 44453
    zones: List[str] = dataclasses.field(
        default_factory=lambda: ["tutorial", "tatooine", "naboo", "corellia"])
    space_zones: List[str] = dataclasses.field(default_factory=list)
    boot_timeout_seconds: int = 1800
    shutdown_timeout_seconds: int = 900

    def validate(self) -> List[str]:
        problems = []
        if not ACCOUNT_NAME.match(self.account):
            problems.append("Account name may only use letters, digits, '-' and '_' (max 32).")
        bad = [z for z in self.zones + self.space_zones if not ZONE_NAME.match(z)]
        if bad:
            problems.append("Invalid zone names: " + ", ".join(bad))
        if not self.zones:
            problems.append("Enable at least one ground zone.")
        return problems

    @classmethod
    def load(cls, path: Path = None) -> "Settings":
        path = path or data_dir() / "settings.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self, path: Path = None) -> None:
        path = path or data_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dataclasses.asdict(self), indent=2), encoding="utf-8")
