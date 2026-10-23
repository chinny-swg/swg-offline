"""Play-style presets, rendered into Lua override files that the server installs before boot.

Three files are written each launch:
  config-offline.lua        -> MMOCoreORB/bin/conf/ (loaded by config-local.lua)
  player_manager-local.lua  -> MMOCoreORB/bin/scripts/managers/
  loot_manager-local.lua    -> MMOCoreORB/bin/scripts/managers/
Each runs after the stock file, so it only needs the values that differ.
"""

import dataclasses
from pathlib import Path
from typing import Dict, List

from .settings import Settings

ADMIN_LEVEL = 15  # Core3's full admin level, as the docker image uses


@dataclasses.dataclass(frozen=True)
class Preset:
    key: str
    title: str
    description: str
    player: Dict[str, float] = dataclasses.field(default_factory=dict)
    loot: Dict[str, float] = dataclasses.field(default_factory=dict)
    admin: bool = False


# "Tuned solo" values are starting points, not tested balance numbers.
PRESETS: Dict[str, Preset] = {p.key: p for p in [
    Preset(
        key="faithful",
        title="Faithful",
        description="Stock Pre-CU rules and rates.",
    ),
    Preset(
        key="tuned-solo",
        title="Tuned solo",
        description="4x XP, more stored pets and droids to fill in for a group, rarer loot twice as common.",
        player={
            "globalExpMultiplier": 4.0,
            "baseStoredCreaturePets": 4,
            "baseStoredFactionPets": 5,
            "baseStoredDroids": 8,
        },
        # Lower values are more frequent (loot rolls random(value) <= chance)
        loot={
            "yellowChance": 500,
            "exceptionalChance": 50000,
            "legendaryChance": 500000,
        },
    ),
    Preset(
        key="sandbox",
        title="Sandbox",
        description="Stock rules, but your account is an admin: /setGodMode, /teleport, /createCreature, /credits...",
        admin=True,
    ),
]}


def _lua_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, (list, tuple)):
        return "{ " + ", ".join(_lua_value(v) for v in value) + " }" if value else "{}"
    raise TypeError(f"cannot render {value!r} as Lua")


def _lua_file(header: str, values: Dict[str, object]) -> str:
    lines = [f"-- {header}", "-- Written by the SWG Offline launcher on every start; edit the launcher settings instead."]
    lines += [f"{name} = {_lua_value(value)}" for name, value in values.items()]
    return "\n".join(lines) + "\n"


def server_config(settings: Settings) -> Dict[str, object]:
    """Core3 config globals the launcher controls (legacy globals override the Core3 table)."""
    return {
        "ZonesEnabled": list(settings.zones),
        "SpaceZonesEnabled": list(settings.space_zones),
        "MakeWeb": 0,
        "AutoReg": 1,
    }


def render(preset: Preset, settings: Settings, out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "config-offline.lua": _lua_file("Server config", server_config(settings)),
        "player_manager-local.lua": _lua_file(f"Preset: {preset.title}", preset.player),
        "loot_manager-local.lua": _lua_file(f"Preset: {preset.title}", preset.loot),
    }
    written = []
    for name, text in files.items():
        path = out_dir / name
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written
