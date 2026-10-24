"""The player's own SWG client: TRE checks, login config, and starting the game."""

import re
import shutil
import subprocess
from pathlib import Path
from typing import List

# The Pre-CU 14.1 set Core3's conf/config.lua loads (TreFiles)
REQUIRED_TRES = [
    "default_patch.tre", "patch_sku1_14_00.tre", "patch_14_00.tre", "patch_sku1_13_00.tre",
    "patch_13_00.tre", "patch_sku1_12_00.tre", "patch_12_00.tre", "patch_11_03.tre",
    "data_sku1_07.tre", "patch_11_02.tre", "data_sku1_06.tre", "patch_11_01.tre",
    "patch_11_00.tre", "data_sku1_05.tre", "data_sku1_04.tre", "data_sku1_03.tre",
    "data_sku1_02.tre", "data_sku1_01.tre", "data_sku1_00.tre", "patch_10.tre",
    "patch_09.tre", "patch_08.tre", "patch_07.tre", "patch_06.tre", "patch_05.tre",
    "patch_04.tre", "patch_03.tre", "patch_02.tre", "patch_01.tre", "patch_00.tre",
    "data_other_00.tre", "data_static_mesh_01.tre", "data_static_mesh_00.tre",
    "data_texture_07.tre", "data_texture_06.tre", "data_texture_05.tre", "data_texture_04.tre",
    "data_texture_03.tre", "data_texture_02.tre", "data_texture_01.tre", "data_texture_00.tre",
    "data_skeletal_mesh_01.tre", "data_skeletal_mesh_00.tre", "data_animation_00.tre",
    "data_sample_04.tre", "data_sample_03.tre", "data_sample_02.tre", "data_sample_01.tre",
    "data_sample_00.tre", "data_music_00.tre", "bottom.tre",
]

LOGIN_CFG = "swgemu_login.cfg"
BACKUP_SUFFIX = ".swg-offline-backup"


def check_install(swg_dir: Path, client_exe: str) -> List[str]:
    """Returns what is missing from the client folder; empty when it is usable."""
    if not swg_dir.is_dir():
        return [f"{swg_dir} is not a folder"]
    problems = []
    if not (swg_dir / client_exe).is_file():
        problems.append(f"{client_exe} not found")
    missing = [t for t in REQUIRED_TRES if not (swg_dir / t).is_file()]
    if missing:
        problems.append(f"{len(missing)} TRE files missing, e.g. {', '.join(missing[:3])}")
    return problems


def set_login_server(text: str, address: str, port: int) -> str:
    """Points loginServerAddress0/loginServerPort0 at address:port, keeping every other line."""
    values = {"loginServerAddress0": address, "loginServerPort0": str(port)}
    lines = text.splitlines()
    seen = set()

    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(loginServerAddress0|loginServerPort0)\s*=", line)
        if m:
            lines[i] = f"{m.group(1)}{m.group(2)}={values[m.group(2)]}"
            seen.add(m.group(2))

    missing = [k for k in values if k not in seen]
    if missing:
        section = next((i for i, l in enumerate(lines) if l.strip().lower() == "[clientgame]"), None)
        if section is None:
            lines += ["[ClientGame]"]
            section = len(lines) - 1
        for offset, key in enumerate(missing, start=1):
            lines.insert(section + offset, f"\t{key}={values[key]}")

    return "\n".join(lines) + "\n"


class LoginConfig:
    """Rewrites swgemu_login.cfg for the session and puts the player's original back afterwards,
    so the SWGEmu launcher and online servers keep working."""

    def __init__(self, swg_dir: Path):
        self.path = swg_dir / LOGIN_CFG
        self.backup = swg_dir / (LOGIN_CFG + BACKUP_SUFFIX)
        self._created = False

    def apply(self, address: str, port: int) -> None:
        # A leftover backup means a previous session crashed; it still holds the original
        if self.path.exists() and not self.backup.exists():
            shutil.copy2(self.path, self.backup)
        self._created = not self.backup.exists()
        original = self.backup.read_text(encoding="latin-1") if self.backup.exists() else ""
        self.path.write_text(set_login_server(original, address, port), encoding="latin-1", newline="\r\n")

    def restore(self) -> None:
        if self.backup.exists():
            shutil.copy2(self.backup, self.path)
            self.backup.unlink()
        elif self._created and self.path.exists():
            self.path.unlink()


def start_client(swg_dir: Path, client_exe: str) -> subprocess.Popen:
    return subprocess.Popen([str(swg_dir / client_exe)], cwd=str(swg_dir))
