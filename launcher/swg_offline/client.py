"""The player's own SWG client: TRE checks, login config, and starting the game."""

import os
import re
import shutil
import struct
import subprocess
import uuid
from pathlib import Path, PureWindowsPath
from typing import List, Mapping, Optional

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
CREATED_SUFFIX = ".swg-offline-created"


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


class LoginConfigError(Exception):
    pass


def is_writable(folder: Path) -> bool:
    """Tries it, once: os.access ignores Windows ACLs, so Program Files looks writable to it. Not
    tempfile either: on Windows it takes PermissionError for a name clash and retries up to
    TMP_MAX (about 2**31) times, which hung the launcher on a Program Files SWG folder."""
    probe = folder / f".swg-offline-write-test-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        fd = os.open(str(probe), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError:
        return False
    os.close(fd)
    try:
        os.unlink(str(probe))
    except OSError:
        pass
    return True


def virtual_store_dir(folder: Path, environ: Mapping[str, str] = os.environ) -> Optional[Path]:
    r"""Where UAC file virtualization sends a legacy program's file access in `folder`:
    C:\Program Files (x86)\SWGEmu -> %LOCALAPPDATA%\VirtualStore\Program Files (x86)\SWGEmu.
    None when the folder is not under Program Files."""
    local = environ.get("LOCALAPPDATA")
    if not local:
        return None
    target = PureWindowsPath(str(folder))
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = environ.get(var) or environ.get(var.upper())
        if not base:
            continue
        base_path = PureWindowsPath(base)
        if target.drive.lower() == base_path.drive.lower() and \
                [p.lower() for p in target.parts[:len(base_path.parts)]] == [p.lower() for p in base_path.parts]:
            return Path(local, "VirtualStore", *target.parts[1:])
    return None


def is_virtualized_exe(exe: Path) -> bool:
    """True for a 32-bit exe without a UAC manifest: Windows virtualizes its file access, so it
    reads a file from the VirtualStore before the real one in Program Files."""
    try:
        data = exe.read_bytes()
    except OSError:
        return False
    if data[:2] != b"MZ" or len(data) < 0x40:
        return False
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return False
    machine = struct.unpack_from("<H", data, pe + 4)[0]
    return machine == 0x14C and b"requestedExecutionLevel" not in data


class LoginConfig:
    """Rewrites swgemu_login.cfg for the session and puts the player's original back afterwards,
    so the SWGEmu launcher and online servers keep working.

    SWGEmu usually lives in Program Files, which the launcher cannot write to. Its client is a
    2005 32-bit exe with no UAC manifest, so Windows looks in the player's VirtualStore first:
    the session's copy goes there and is removed again afterwards."""

    def __init__(self, swg_dir: Path, client_exe: str = "SWGEmu.exe",
                 environ: Mapping[str, str] = os.environ):
        self.swg_dir = swg_dir
        self.client_exe = client_exe
        self.environ = environ
        self._use(swg_dir)
        self._created = False

    def _use(self, folder: Path) -> None:
        self.path = folder / LOGIN_CFG
        self.backup = folder / (LOGIN_CFG + BACKUP_SUFFIX)
        # Marks a file this launcher created, so a crashed session's copy is not kept as the original
        self.marker = folder / (LOGIN_CFG + CREATED_SUFFIX)

    def prepare(self) -> None:
        """Decides where the session's login config goes. Raises LoginConfigError if nowhere the
        client would read it is writable."""
        if is_writable(self.swg_dir):
            self._use(self.swg_dir)
            return
        virtual = virtual_store_dir(self.swg_dir, self.environ)
        if virtual is None or not is_virtualized_exe(self.swg_dir / self.client_exe):
            raise LoginConfigError(
                f"The launcher can't write to your SWG folder ({self.swg_dir}). Move the folder "
                "somewhere you own, such as C:\\SWGEmu, and choose it again in Settings.")
        virtual.mkdir(parents=True, exist_ok=True)
        self._use(virtual)

    def apply(self, address: str, port: int) -> None:
        if self.marker.exists() and not self.backup.exists():
            # A previous session crashed after creating this file: it is ours, not the player's
            self.path.unlink(missing_ok=True)
        # A leftover backup means a previous session crashed; it still holds the original
        if self.path.exists() and not self.backup.exists():
            shutil.copy2(self.path, self.backup)
        self._created = not self.backup.exists()
        if self.backup.exists():
            original = self.backup.read_text(encoding="latin-1")
        else:
            # Nothing at the write location yet (a fresh VirtualStore): start from the real file
            real = self.swg_dir / LOGIN_CFG
            original = real.read_text(encoding="latin-1") if real != self.path and real.exists() else ""
        if self._created:
            self.marker.touch()
        self.path.write_text(set_login_server(original, address, port), encoding="latin-1", newline="\r\n")

    def restore(self) -> None:
        if self.backup.exists():
            shutil.copy2(self.backup, self.path)
            self.backup.unlink()
        elif (self._created or self.marker.exists()) and self.path.exists():
            self.path.unlink()
        self.marker.unlink(missing_ok=True)


def start_client(swg_dir: Path, client_exe: str) -> subprocess.Popen:
    return subprocess.Popen([str(swg_dir / client_exe)], cwd=str(swg_dir))
