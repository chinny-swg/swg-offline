"""One play session: boot the server, run the client, save and stop the server."""

import enum
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional

from . import client, native, presets, wsl
from .server import ServerProcess
from .settings import Settings, data_dir


class Stage(enum.Enum):
    CHECKING = "Checking your SWG install"
    BOOTING = "Starting the galaxy"
    PLAYING = "Playing"
    SAVING = "Saving the galaxy"
    DONE = "Done"
    FAILED = "Failed"


class SessionError(Exception):
    pass


StatusCallback = Callable[[Stage, str], None]


class Session:
    """Runs on a worker thread; the GUI or CLI listens through `status`."""

    def __init__(self, settings: Settings, status: StatusCallback,
                 server_args: Optional[List[str]] = None,
                 start_client: Callable[[Path, str], subprocess.Popen] = client.start_client,
                 resolve_address: Callable[[str], str] = wsl.resolve_address,
                 home: Optional[Path] = None):
        self.settings = settings
        self.status = status
        self.cancelled = threading.Event()
        self._server_args = server_args  # tests pass their own server command
        self._start_client = start_client
        self._resolve_address = resolve_address
        self.home = home or data_dir()
        self.server: Optional[ServerProcess] = None
        self.client: Optional[subprocess.Popen] = None

    @property
    def server_log(self) -> Path:
        return self.home / "logs" / "server.log"

    def cancel(self) -> None:
        """Stops waiting for boot, or ends the session as if the client had closed."""
        self.cancelled.set()

    def run(self) -> None:
        login = client.LoginConfig(Path(self.settings.swg_dir))
        error = None
        saved = True
        try:
            self._play(login)
        except SessionError as e:
            error = str(e)
        except Exception as e:  # anything unexpected still has to reach the player
            error = f"{type(e).__name__}: {e}"
        finally:
            login.restore()
            if self.server is not None and not self.server.exited.is_set():
                self.status(Stage.SAVING, "Do not turn off your PC.")
                saved = self.server.stop(self.settings.shutdown_timeout_seconds)

        if error:
            self.status(Stage.FAILED, error)
        elif not saved:
            self.status(Stage.FAILED, "The server did not save in time and was stopped. See " + str(self.server_log))
        else:
            self.status(Stage.DONE, "Galaxy saved.")

    def _play(self, login: client.LoginConfig) -> None:
        s = self.settings
        swg_dir = Path(s.swg_dir)

        backend = s.resolved_backend()
        server_dir = s.resolved_server_dir()

        self.status(Stage.CHECKING, "")
        problems = s.validate() + client.check_install(swg_dir, s.client_exe)
        if backend == "native":
            problems += native.check_server(server_dir)
        if s.preset not in presets.PRESETS:
            problems.append(f"Unknown preset '{s.preset}'")
        if problems:
            raise SessionError("\n".join(problems))
        preset = presets.PRESETS[s.preset]
        overrides = self.home / "overrides"
        presets.render(preset, s, overrides)
        admin_level = presets.ADMIN_LEVEL if preset.admin else 0

        if backend == "native":
            # Same PC, so UDP on loopback just works; the galaxy row is created with 127.0.0.1
            address = "127.0.0.1"
            native.install(server_dir, overrides, s)
            args = self._server_args or [str(server_dir / native.SERVER_EXE)]
            cwd = server_dir
            # Listen on loopback only: nothing outside the PC can connect, and no firewall prompt
            env = dict(os.environ, CORE3_BIND_ADDRESS=address)
        else:
            address = s.address if s.address != "auto" else self._resolve_address(s.wsl_distro)
            args = self._server_args or wsl.server_args(s.wsl_distro, address, overrides,
                                                        s.account, admin_level)
            cwd = None
            env = None

        self.status(Stage.BOOTING, f"{preset.title} · {len(s.zones)} planets · {address}")
        self.server = ServerProcess(args, self.server_log,
                                    on_line=lambda line: self.status(Stage.BOOTING, line), cwd=cwd, env=env)
        self.server.start()
        if not self.server.wait_ready(s.boot_timeout_seconds, self.cancelled):
            if self.cancelled.is_set():
                raise SessionError("Cancelled.")
            if self.server.exited.is_set():
                raise SessionError("The server stopped while starting:\n"
                                   + "\n".join(list(self.server.tail)[-12:]))
            raise SessionError(f"The server did not finish starting in {s.boot_timeout_seconds} s.")
        self.server.on_line = None

        if backend == "native":
            # The server has created its database by now
            native.apply_admin(server_dir / native.DB_PATH, s.account, admin_level)

        login.apply(address, s.login_port)
        self.status(Stage.PLAYING, f"Log in as '{s.account}'. Your first login sets its password.")
        self.client = self._start_client(swg_dir, s.client_exe)
        while self.client.poll() is None and not self.cancelled.is_set():
            if self.server.exited.wait(1):
                raise SessionError("The server stopped during play. See " + str(self.server_log))
