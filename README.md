# swg-offline

Play Pre-CU Star Wars Galaxies on one Windows PC with no internet and no server window.

SWG's client holds no game rules, so this isn't serverless. A launcher starts a
[Core3](https://github.com/chinny-swg/Core3) server hidden in the background, waits until it is
ready, starts your client against it, and saves and stops the server when you quit. To you it is
an offline game.

```
SWGOffline.exe ──starts hidden──▶ core3 (native core3.exe on SQLite, or Core3 in WSL2 + MariaDB)
      │                               ▲
      └──starts──▶ SWGEmu.exe ──UDP───┘  this PC only
```

Everything offline-specific lives in this repo. Core3 is used as-is at a pinned commit, with the
patches in [`core3/`](core3/) applied at build time; the Core3 fork itself is never changed.

## Two ways to run the server

| | Native (installer) | WSL2 |
|---|---|---|
| Server | `core3.exe` built with MSVC | Core3 built inside Debian on WSL2 |
| Database | SQLite file, no database server | MariaDB |
| Setup | Run `SWGOffline-Setup.exe` | `windows\install.bat` (builds Core3, takes a while) |
| Extra installs | None | WSL2 |
| Status | Built by CI; not yet played end to end | Phases 1–2 of the report |

The launcher uses the native server when `server\core3.exe` sits next to it, else WSL
(`backend` in the settings).

## What you need

- Windows 10/11, 64-bit, 8 GB RAM minimum (16 GB is comfortable).
- Your own SWGEmu-patched Pre-CU 14.1 client folder, with `SWGEmu.exe` and the 51 TRE files
  Core3's `conf/config.lua` lists. Nothing here ships SOE files.
- Internet once, during setup. After that, unplug.

## Native install

Download `SWGOffline-Setup` from the latest [Build](../../actions/workflows/build.yml) run's
artifacts and run it. It installs per user (no admin), asks for your SWG folder and checks it,
and never copies or ships SOE files: the server reads the TREs in place.

The native server:

- uses SQLite (`DBType = "sqlite"`), created on first start in `server\databases\`;
- listens on 127.0.0.1 only (`CORE3_BIND_ADDRESS`), so nothing outside the PC can connect and
  Windows shows no firewall prompt;
- saves and shuts down if the launcher goes away (`ShutdownOnConsoleEOF`).

Saved characters stay in `server\databases\` when you uninstall.

## WSL2 install

1. Open an administrator command prompt and run `windows\install.bat`.
   - Without WSL, it installs WSL with Debian and asks you to reboot. Run it again afterwards.
   - Then it runs `server/wsl/setup.sh` as root inside Debian: Core3's own
     `linux/bootstrap.sh` at the pinned commit (packages, MariaDB, schema, copying your TREs to
     `/tre`), this repo's patches, the build, and `swg-offline-server`.
2. Start the game with `windows\SWG Offline.cmd` (needs Python 3.9+ from python.org).

`install.bat --commit <sha>` builds another Core3 commit; the patches must still apply to it.

## Play

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

Each start, the launcher writes three Lua files and installs them into the server before it
boots; each runs after the stock file it adjusts:

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
| Core3 pin and patches | `core3/` | Which Core3 commit is built, and the changes applied to it (below) |
| Native build | `.github/workflows/build.yml`, `core3/windows/vcpkg.json` | `core3.exe` with MSVC, vcpkg libraries and SQLite; the installer |
| Installer | `windows/installer.iss` | Inno Setup script: launcher + `server\` (Core3's `bin/` and `core3.exe`) |
| `swg-offline-server` | `server/wsl/`, installed to `/usr/local/bin` | WSL: start MariaDB, install the overrides, set the `galaxy` address and admin level, run `core3` with its console on a fifo, save on exit |
| `setup.sh` | `server/wsl/` | WSL: one-time provisioning and build |
| `install.bat`, `SWG Offline.cmd`, `build-exe.bat` | `windows/` | Windows entry points for the WSL path |

### Core3 patches

`core3/pin` names the Core3 commit; `core3/apply-patches.sh <Core3 checkout>` applies, in order:

| Patch | What it adds |
|---|---|
| `core3/0001-manager-local-overrides` | `player_manager-local.lua` / `loot_manager-local.lua`, used by the presets |
| `core3/0002-sqlite-backend` | `DBType = "sqlite"`: a single-file database with the MySQL-flavoured SQL translated, MySQL optional at build time |
| `core3/0003-msvc-build` | `/bigobj` and pthreads for the MSVC build |
| `core3/0004-shutdown-on-console-eof` | `ShutdownOnConsoleEOF`: save and stop when the launcher goes away |
| `core3/0005-sqlite-unit-tests` | gtest coverage for the SQLite backend |
| `core3/0006-windows-build-fixes` | `uint` → `uint32`, a stale Windows-only branch in `PlanetTravelPointList`, portable `mkdir` |
| `core3/0007-msvc-full-types-in-generated-headers` | MSVC needs the full types behind `Reference<>` members, so six generated headers include instead of forward-declare |
| `engine3/0001-opt-in-bind-address` | `CORE3_BIND_ADDRESS`: listen on one address only |
| `engine3/0002-windows-fromiso8601` | Windows has no `strptime()`; parse ISO 8601 times without it |
| `engine3/0003-msvc-build-fixes` | MSVC: 64-bit detection, `__PRETTY_FUNCTION__`, `libgen.h`, a missing `<sstream>` |

To move to a newer Core3, change `CORE3_COMMIT`, run the script on a fresh checkout, and refresh
any patch that no longer applies (`--reverse` takes the series back out).

### Things the launcher handles for you

- **The address.** Native: 127.0.0.1. WSL2's default NAT mode forwards only TCP on `localhost`
  into WSL, and SWG talks UDP, so there the launcher uses `127.0.0.1` when `.wslconfig` has
  `networkingMode=mirrored`, and the WSL VM's own address otherwise. The VM's address is on a
  host-only virtual network, not the internet.
- **Your client config.** `swgemu_login.cfg` is backed up and rewritten for the session, then
  restored afterwards. The SWGEmu launcher and online servers keep working.
- **Clean shutdown.** The server is never killed while it saves unless it overruns
  `shutdown_timeout_seconds` (15 minutes).
- **Logs.** The server console is written to `%LOCALAPPDATA%\SWGOffline\logs\server.log`.

Settings live in `%LOCALAPPDATA%\SWGOffline\settings.json`, which also holds `backend`,
`server_dir`, `wsl_distro`, `address`, `boot_timeout_seconds` and `space_zones`.

## Development

```
cd launcher
python -m unittest discover -s tests -t .
```

The tests run whole sessions (WSL and native) against a fake `core3`, and the real
`swg-offline-server` script with MariaDB stubbed out (Linux only). CI runs them on Linux and
Windows, builds `core3.exe`, smoke-tests it on a fresh SQLite database, and builds the installer.

## Not done yet

- **Scaling group content** (NPC health and damage in `scripts/mobile/`). No preset touches it.

## Legal

Use your own copy of the game. Never redistribute the TREs or the client. Core3 is AGPL-3.0: the
installer's server is Core3 plus the patches in `core3/`, which is its source. This is not legal
advice.
