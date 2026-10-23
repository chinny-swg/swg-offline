"""Stands in for core3: prints boot lines, the READY prompt, then obeys save/exit on stdin.

FAKE_CORE3_FAIL=1 makes it die during boot. FAKE_CORE3_LOG=path records the commands it got.
FAKE_CORE3_SQLITE=path creates an accounts table there before READY, like DBType = "sqlite".
"""

import os
import sys

log = os.environ.get("FAKE_CORE3_LOG")


def record(line):
    if log:
        with open(log, "a") as f:
            f.write(line + "\n")


print("[Core] Server start, pid: 1, bind=" + os.environ.get("CORE3_BIND_ADDRESS", "any"), flush=True)
print("[ZoneServer] loading tatooine", flush=True)
if os.environ.get("FAKE_CORE3_FAIL"):
    print("[Core] FATAL: could not open tre files", flush=True)
    sys.exit(3)
db = os.environ.get("FAKE_CORE3_SQLITE")
if db:
    # Like Core3 with DBType = "sqlite": the database exists once the server is up
    import sqlite3
    os.makedirs(os.path.dirname(db), exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS accounts (account_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " username TEXT NOT NULL, admin_level INTEGER NOT NULL DEFAULT 0)")
    con.commit()
    con.close()
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
