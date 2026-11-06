# swg-offline (discontinued)

> **This project is no longer maintained, and the repository is archived.**
>
> To play on your own PC, run Core3 in Docker Desktop on WSL 2 and connect with the SWGEmu client
> instead. See **[Local Server on Windows (WSL + Docker)](https://chinny-swg.github.io/guides/windows-local-server/)**.

swg-offline tried to make Pre-CU Star Wars Galaxies playable on one Windows PC with no visible
server. A launcher started a hidden [Core3](https://github.com/chinny-swg/Core3) server, pointed
the client at it, and saved and stopped the server when the player quit. It came in two forms:
native, a patched `core3.exe` on SQLite built with MSVC, and Core3 inside WSL2.

It never reached a full play session on Windows, and it was dropped in favour of the standard
Docker workflow above.

The code is kept here as it was. `launcher/` holds the launcher, `core3/` the pinned Core3 commit
and the patches applied to it, `windows/` the installer and the WSL scripts, and
`.github/workflows/` the build. Core3 is AGPL-3.0, and these patches are the source of the
binaries this repository's CI built.
