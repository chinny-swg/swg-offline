# swg-offline

Play Pre-CU Star Wars Galaxies on one Windows PC with no internet and no server window.

SWG's client holds no game rules, so this isn't serverless. A launcher starts your
[Core3 fork](https://github.com/chinny-swg/Core3) hidden in the background, waits until it is
ready, starts your client against it, and saves and stops the server when you quit. To you it is
an offline game.

```
SWGOffline.exe ──starts hidden──▶ Core3 in WSL2 (+ MariaDB)
      │                               ▲
      └──starts──▶ SWGEmu.exe ──UDP───┘  (this PC only: loopback or the WSL virtual network)
```

This covers phases 1 and 2 of the
[feasibility report](https://claude.ai/artifact/TsASQATdCN48aZqkWWDLq4): the server runs in
WSL2, and the launcher hides it.

## What you need

- Windows 10/11, 64-bit, 8 GB RAM minimum (16 GB is comfortable).
- Your own SWGEmu-patched Pre-CU 14.1 client folder, with `SWGEmu.exe` and the 51 TRE files
  Core3's `conf/config.lua` lists. Nothing here ships SOE files.
- Python 3.9+ from python.org, or a `SWGOffline.exe` built with `windows\build-exe.bat`.
- Internet once, during setup. After that, unplug.

## Set up (once)

1. Open an administrator command prompt and run `windows\install.bat`.
   - Without WSL, it installs WSL with Debian and asks you to reboot. Run it again afterwards.
   - Then it runs `server/wsl/setup.sh` as root inside Debian. That script runs your fork's own
     `linux/bootstrap.sh` (packages, MariaDB, schema, `config-local.lua`, and copying your TREs to
     `/tre`; it asks for your SWG folder if it can't find it), then builds Core3, then installs
     `swg-offline-server`.
2. Setup builds the `unstable` branch. To build another branch:
   `install.bat --branch my-branch` (or `--repo https://github.com/someone`).

> The Tuned solo preset needs the Core3 change that loads
> `scripts/managers/player_manager-local.lua` and `loot_manager-local.lua`
> (branch `claude/artifact-implementation-hcwy4k` on the fork). Until that is merged into
> `unstable`, set up with `install.bat --branch claude/artifact-implementation-hcwy4k`.
> Without it, Tuned solo plays like Faithful.

## Play

Double-click `windows\SWG Offline.cmd`, or `SWGOffline.exe`.

1. Pick your SWG folder, an account name, a play style and which planets to load.
2. Press **Play**. The launcher shows the server's progress while the planets load. This takes
   minutes, and fewer planets boot faster.
3. The client opens. Log in with your account name. With `AutoReg`, the first login creates the
   account, and whatever password you type becomes its password.
4. Quit the game. The launcher saves the galaxy (`save`, then `exit` on the Core3 console) and
   closes the server. Don't turn the PC off while it says *Saving*.

Closing the launcher mid-game asks first, then saves the same way. If the launcher crashes, the
server notices its console has closed and also saves and exits.

There is also a console mode. From the `launcher` folder, run
`py -3 -m swg_offline --cli --preset tuned-solo --zones tutorial,tatooine,naboo`.

### Play styles

| Preset | What changes |
|---|---|
| **Faithful** | Nothing. Stock Pre-CU rules. |
| **Tuned solo** | `globalExpMultiplier` 4, more stored pets (4), faction pets (5) and droids (8), and yellow, exceptional and legendary loot twice as common. These are starting points, not tested balance. |
| **Sandbox** | Stock rules, but your account gets admin level 15, so `/setGodMode`, `/teleport`, `/createCreature`, `/credits` and the rest work. |

Each start, the launcher writes three Lua files to `%LOCALAPPDATA%\SWGOffline\overrides\`. The
server copies them into Core3 before it boots, and each one runs after the stock file it adjusts:

| File | Goes to | Holds |
|---|---|---|
| `config-offline.lua` | `bin/conf/` (loaded by `config-local.lua`) | `ZonesEnabled`, `SpaceZonesEnabled` (none by default), `MakeWeb = 0`, `AutoReg = 1` |
| `player_manager-local.lua` | `bin/scripts/managers/` | the preset's player values |
| `loot_manager-local.lua` | `bin/scripts/managers/` | the preset's loot values |

To add or change a preset, edit `PRESETS` in `launcher/swg_offline/presets.py`.

## How it fits together

| Piece | Where | Job |
|---|---|---|
| Launcher | `launcher/swg_offline/` (Python stdlib + tkinter) | Settings, TRE check, preset files, start and stop the server, point the client at it |
| `swg-offline-server` | `server/wsl/`, installed to `/usr/local/bin` | Start MariaDB, install the overrides, set the `galaxy` address and admin level, run `core3` with its console on a fifo, save on exit, stop MariaDB |
| `setup.sh` | `server/wsl/` | One-time provisioning and build |
| `install.bat`, `SWG Offline.cmd`, `build-exe.bat` | `windows/` | Windows entry points |

Things the launcher handles for you:

- **The address.** WSL2's default NAT mode forwards only TCP on `localhost` into WSL, and SWG
  talks UDP. So the launcher uses `127.0.0.1` when `.wslconfig` has `networkingMode=mirrored`,
  and the WSL VM's own address otherwise. The `galaxy` table and the client's
  `swgemu_login.cfg` always get the same address. The VM's address is on a host-only virtual
  network, not the internet.
- **Your client config.** `swgemu_login.cfg` is backed up and rewritten for the session, then
  restored afterwards. The SWGEmu launcher and online servers keep working.
- **Clean shutdown.** The server is never killed while it saves unless it overruns
  `shutdown_timeout_seconds` (15 minutes).
- **Logs.** The server console is written to `%LOCALAPPDATA%\SWGOffline\logs\server.log`.
  Core3's own logs stay in `MMOCoreORB/bin/log/` inside WSL.

Settings live in `%LOCALAPPDATA%\SWGOffline\settings.json`, which also holds `wsl_distro`,
`address` (`auto` or a fixed IP), `boot_timeout_seconds` and `space_zones`.

## Development

```
cd launcher
python -m unittest discover -s tests -t .
```

The tests run a whole session against a fake `core3`. They also run the real
`swg-offline-server` script with MariaDB stubbed out, which needs Linux.

## Not done yet

From the report's later phases:

- **Native Windows server (phase 3).** Build engine3 and Core3 with MSVC and vcpkg, then point
  the launcher at `core3.exe` instead of WSL. `Session` already accepts a custom server command.
- **No separate database (phase 4).** Either a portable MariaDB, or a SQLite backend in
  `src/server/db/`.
- **Installer (phase 5).** For now, `install.bat` plus the folder picker stand in.
- **Scaling group content (NPC health and damage in `scripts/mobile/`).** No preset touches it.

## Legal

Use your own copy of the game. Never redistribute the TREs or the client. Core3 is AGPL-3.0: if
you share a modified server, share its source too. This is not legal advice.
