"""Running the server inside WSL2."""

import configparser
import ipaddress
import os
import re
import subprocess
from pathlib import Path, PureWindowsPath
from typing import List, Optional

SERVER_COMMAND = "/usr/local/bin/swg-offline-server"

# Keeps wsl.exe from flashing a console window (subprocess.CREATE_NO_WINDOW, Windows only)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def to_wsl_path(path: str) -> str:
    r"""C:\Games\SWG -> /mnt/c/Games/SWG (WSL's default automount root)."""
    p = PureWindowsPath(path)
    if not p.drive or not re.match(r"^[A-Za-z]:$", p.drive):
        raise ValueError(f"not a local drive path: {path}")
    return "/".join(["/mnt", p.drive[0].lower()] + list(p.parts[1:]))


def mirrored_networking(wslconfig_text: str) -> bool:
    """True when .wslconfig sets networkingMode=mirrored, where 127.0.0.1 reaches WSL over UDP too."""
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read_string(wslconfig_text)
    except configparser.Error:
        return False
    return parser.get("wsl2", "networkingMode", fallback="").strip().lower() == "mirrored"


def first_ipv4(hostname_output: str) -> Optional[str]:
    for token in hostname_output.split():
        try:
            if isinstance(ipaddress.ip_address(token), ipaddress.IPv4Address):
                return token
        except ValueError:
            continue
    return None


def wsl_args(distro: str, *command: str) -> List[str]:
    return ["wsl.exe", "-d", distro, "-u", "root", "--", *command]


def resolve_address(distro: str) -> str:
    """The address both the galaxy table and the client must use.

    In WSL2's default NAT mode, Windows only forwards TCP on localhost into the VM, and SWG
    talks UDP, so the client has to use the VM's own (host-only, never internet) address.
    """
    wslconfig = Path(os.environ.get("USERPROFILE", Path.home())) / ".wslconfig"
    try:
        if mirrored_networking(wslconfig.read_text(encoding="utf-8", errors="replace")):
            return "127.0.0.1"
    except OSError:
        pass

    out = subprocess.run(wsl_args(distro, "hostname", "-I"), capture_output=True, text=True,
                         timeout=120, creationflags=NO_WINDOW)
    address = first_ipv4(out.stdout)
    if out.returncode != 0 or not address:
        raise RuntimeError(f"Could not get the WSL address from distro '{distro}': "
                           f"{(out.stderr or out.stdout).strip() or 'no IPv4 address'}")
    return address


def server_args(distro: str, address: str, overrides_dir: Path, account: str,
                admin_level: int) -> List[str]:
    return wsl_args(distro, SERVER_COMMAND,
                    "--address", address,
                    "--overrides", to_wsl_path(str(overrides_dir)),
                    "--admin-user", account,
                    "--admin-level", str(admin_level))
