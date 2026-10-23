"""The hidden Core3 process: start it, watch its console, shut it down cleanly."""

import collections
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional

# Core3 prints this console prompt once boot has finished and the login server is listening
READY_LINE = "READY"

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ServerProcess:
    def __init__(self, args: List[str], log_path: Path,
                 on_line: Optional[Callable[[str], None]] = None):
        self.args = args
        self.log_path = log_path
        self.on_line = on_line
        self.ready = threading.Event()
        self.exited = threading.Event()
        self.tail = collections.deque(maxlen=40)
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None

    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen(
            self.args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=NO_WINDOW)
        self._reader = threading.Thread(target=self._read, name="server-console", daemon=True)
        self._reader.start()

    def _read(self) -> None:
        with open(self.log_path, "w", encoding="utf-8") as log:
            for raw in self._proc.stdout:
                line = raw.rstrip("\r\n")
                log.write(line + "\n")
                log.flush()
                self.tail.append(line)
                if line.strip() == READY_LINE:
                    self.ready.set()
                if self.on_line:
                    self.on_line(line)
        self._proc.stdout.close()
        self._proc.wait()
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        self.exited.set()

    @property
    def returncode(self) -> Optional[int]:
        return self._proc.returncode if self._proc else None

    def wait_ready(self, timeout: float, cancelled: threading.Event) -> bool:
        """Blocks until READY, exit, timeout or cancel. True only when the server is ready."""
        waited = 0.0
        while waited < timeout and not cancelled.is_set():
            if self.ready.wait(0.5):
                return True
            if self.exited.is_set():
                return False
            waited += 0.5
        return False

    def send(self, command: str) -> bool:
        try:
            self._proc.stdin.write(command + "\n")
            self._proc.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def stop(self, timeout: float) -> bool:
        """Saves and exits. Returns False if the server had to be killed."""
        if self._proc is None or self.exited.is_set():
            return True
        self.send("save")
        self.send("exit")
        try:
            self._proc.stdin.close()
        except OSError:
            pass  # already gone; under WSL the server side turns stdin EOF into "exit" anyway
        if self.exited.wait(timeout):
            return True
        self._proc.kill()
        self.exited.wait(10)
        return False
