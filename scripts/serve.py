"""Start the MCR Dashboard on a fixed port, resolving any conflict first.

  python scripts/serve.py                 # dev: start on MCR_PORT (default 8503)
  python scripts/serve.py --prod          # headless, no file watcher
  python scripts/serve.py --rollback      # restart whatever this script last stopped
  python scripts/serve.py --kill-foreign  # ALSO stop a non-MCR process holding the port (off by default)

Conflict policy
  * An older MCR Dashboard instance on the port is stopped (logged to logs/conflicts.log, command saved for rollback).
  * Any other program on the port is left alone; MCR moves to the next free port and says so. Pass --kill-foreign
    only if you are sure that program should go.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "conflicts.log"
LAST = ROOT / "data" / "last_stopped.json"
PIDFILE = ROOT / "data" / "mcr.pid"


def log(msg: str) -> None:
    LOG.parent.mkdir(exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(LOG, "a", encoding="utf8") as f:
        f.write(line + "\n")


def listener(port: int):
    for c in psutil.net_connections(kind="inet"):
        if c.status == psutil.CONN_LISTEN and c.laddr.port == port and c.pid:
            try:
                return psutil.Process(c.pid)
            except psutil.NoSuchProcess:
                return None
    return None


def is_mcr(p: psutil.Process) -> bool:
    try:
        cmd = " ".join(p.cmdline()).lower()
        cwd = (p.cwd() or "").lower()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return False
    return "streamlit" in cmd and "app.py" in cmd and (str(ROOT).lower() in cmd or cwd == str(ROOT).lower())


def stop(p: psutil.Process) -> None:
    kids = p.children(recursive=True)
    for q in [p, *kids]:
        try:
            q.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs([p, *kids], timeout=8)
    for q in alive:
        q.kill()


def free_port(start: int) -> int:
    for port in range(start, start + 20):
        if not listener(port):
            return port
    raise SystemExit("no free port found in range")


def resolve(port: int, kill_foreign: bool) -> int:
    holder = listener(port)
    if not holder:
        return port
    cmd = " ".join(holder.cmdline())
    if is_mcr(holder):
        log(f"CONFLICT port {port}: old MCR Dashboard pid={holder.pid} cmd={cmd!r} -> stopping it")
        LAST.parent.mkdir(exist_ok=True)
        LAST.write_text(json.dumps({"cmdline": holder.cmdline(), "cwd": holder.cwd(), "port": port}), encoding="utf8")
        stop(holder)
        time.sleep(1)
        return port
    if kill_foreign:
        log(f"CONFLICT port {port}: foreign process pid={holder.pid} cmd={cmd!r} -> stopping it (--kill-foreign)")
        LAST.write_text(json.dumps({"cmdline": holder.cmdline(), "cwd": holder.cwd(), "port": port}), encoding="utf8")
        stop(holder)
        time.sleep(1)
        return port
    new = free_port(port + 1)
    log(f"CONFLICT port {port}: held by another program pid={holder.pid} cmd={cmd!r}. NOT stopping it; using port {new} instead")
    return new


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=int(os.environ.get("MCR_PORT", 8503)))
    ap.add_argument("--prod", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    ap.add_argument("--kill-foreign", action="store_true")
    a = ap.parse_args()

    if a.rollback:
        if not LAST.exists():
            print("nothing to roll back (no instance was stopped by serve.py)")
            return 1
        d = json.loads(LAST.read_text(encoding="utf8"))
        log(f"ROLLBACK: restarting {d['cmdline']!r} in {d['cwd']!r}")
        subprocess.Popen(d["cmdline"], cwd=d["cwd"])
        return 0

    port = resolve(a.port, a.kill_foreign)
    cmd = [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.port", str(port), "--server.headless", "true"]
    if a.prod:
        cmd += ["--server.fileWatcherType", "none", "--browser.gatherUsageStats", "false"]
    log(f"starting MCR Dashboard on http://localhost:{port} ({'prod' if a.prod else 'dev'})")
    proc = subprocess.Popen(cmd, cwd=ROOT)
    PIDFILE.write_text(json.dumps({"pid": proc.pid, "port": port}), encoding="utf8")
    try:
        return proc.wait()
    except KeyboardInterrupt:
        stop(psutil.Process(proc.pid))
        return 0


if __name__ == "__main__":
    sys.exit(main())
