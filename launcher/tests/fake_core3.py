"""Stands in for core3: prints boot lines, the READY prompt, then obeys save/exit on stdin.

FAKE_CORE3_FAIL=1 makes it die during boot. FAKE_CORE3_LOG=path records the commands it got.
"""

import os
import sys

log = os.environ.get("FAKE_CORE3_LOG")


def record(line):
    if log:
        with open(log, "a") as f:
            f.write(line + "\n")


print("[Core] Server start, pid: 1", flush=True)
print("[ZoneServer] loading tatooine", flush=True)
if os.environ.get("FAKE_CORE3_FAIL"):
    print("[Core] FATAL: could not open tre files", flush=True)
    sys.exit(3)
print("[Core] initialized", flush=True)
print("\nREADY\n> ", end="", flush=True)

for line in sys.stdin:
    cmd = line.strip()
    record(cmd)
    if cmd == "save":
        print("saving", flush=True)
    elif cmd == "exit":
        print("[Core] database backup done", flush=True)
        sys.exit(0)
    print("\nREADY\n> ", end="", flush=True)

record("<eof>")
sys.exit(5)
