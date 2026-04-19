#!/usr/bin/env python3
"""PMON-AI-OPS Unified Service Manager

Usage:
    python pmon.py start       # Start all services (backend + frontend + proxy)
    python pmon.py stop        # Stop all services
    python pmon.py restart     # Stop then start
    python pmon.py status      # Show running services
    python pmon.py logs        # Tail logs (Ctrl+C to exit)
"""

import subprocess
import sys
import time
import os
import signal
import json
import urllib.request
import urllib.error
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
BACKEND_DIR  = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

BACKEND_PORT = 8000
VITE_PORT    = 5173
PROXY_PORT   = 10444   # HTTP proxy for phtunnel (peanut shell)

PID_FILE = PROJECT_ROOT / ".pmon_pids.json"


# ── Helpers ────────────────────────────────────────────────────
def log(tag, msg, color=None):
    colors = {"ok": "\033[92m", "err": "\033[91m", "warn": "\033[93m", "info": "\033[96m"}
    c = colors.get(color, "")
    reset = "\033[0m" if c else ""
    print(f"  [{tag}] {c}{msg}{reset}", flush=True)


def save_pids(pids: dict):
    PID_FILE.write_text(json.dumps(pids, indent=2), encoding="utf-8")


def load_pids() -> dict:
    if PID_FILE.exists():
        try:
            return json.loads(PID_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def is_port_listening(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(port: int, timeout: float = 20) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_port_listening(port):
            return True
        time.sleep(0.5)
    return False


def kill_proc(pid: int, timeout: float = 5):
    """Kill a process by PID. Uses taskkill on Windows for reliability."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=timeout)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.3)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def kill_port(port: int):
    """Kill any process listening on a given port (Windows)."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                log("KILL", f"Port {port} -> PID {pid}", "warn")
                kill_proc(pid)
    except Exception as e:
        log("ERR", f"kill_port({port}): {e}", "err")


# ── Commands ───────────────────────────────────────────────────

def cmd_start():
    print("\n" + "=" * 50)
    print("  PMON-AI-OPS  Starting Services")
    print("=" * 50 + "\n")

    pids = {}

    # 1. Clean old processes
    log("CLEAN", "Stopping old processes...", "info")
    kill_port(BACKEND_PORT)
    kill_port(VITE_PORT)
    kill_port(PROXY_PORT)
    time.sleep(1)

    # 2. Ensure tftp_receive dir
    tftp_dir = BACKEND_DIR / "tftp_receive"
    tftp_dir.mkdir(exist_ok=True)

    # 3. Start backend
    log("BACKEND", f"Starting FastAPI on :{BACKEND_PORT}...", "info")
    backend_log = PROJECT_ROOT / "logs" / "backend.log"
    backend_log.parent.mkdir(exist_ok=True)

    backend_proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "uvicorn",
         "src.main:app", "--host", "0.0.0.0", "--port", str(BACKEND_PORT)],
        cwd=str(BACKEND_DIR),
        stdout=open(backend_log, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    pids["backend"] = backend_proc.pid
    log("BACKEND", f"PID={backend_proc.pid}", "info")

    if wait_for_port(BACKEND_PORT):
        log("BACKEND", f"Listening on :{BACKEND_PORT}", "ok")
    else:
        log("BACKEND", "FAILED to start", "err")
        cmd_stop()
        return

    # 4. Start frontend
    log("FRONTEND", f"Starting Vite on :{VITE_PORT}...", "info")
    frontend_log = PROJECT_ROOT / "logs" / "frontend.log"

    frontend_proc = subprocess.Popen(
        ["cmd", "/c", f"npx vite --host 0.0.0.0 --port {VITE_PORT}"],
        cwd=str(FRONTEND_DIR),
        stdout=open(frontend_log, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    pids["frontend"] = frontend_proc.pid
    log("FRONTEND", f"PID={frontend_proc.pid}", "info")

    if wait_for_port(VITE_PORT):
        log("FRONTEND", f"Listening on :{VITE_PORT}", "ok")
    else:
        log("FRONTEND", "FAILED to start", "err")
        cmd_stop()
        return

    # 5. Start HTTP proxy (for phtunnel)
    log("PROXY", f"Starting HTTP proxy on :{PROXY_PORT} -> :{VITE_PORT}...", "info")
    proxy_script = PROJECT_ROOT / "tools" / "http_proxy.py"
    proxy_log = PROJECT_ROOT / "logs" / "proxy.log"

    if proxy_script.exists():
        proxy_proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(proxy_script)],
            cwd=str(PROJECT_ROOT),
            stdout=open(proxy_log, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
        pids["proxy"] = proxy_proc.pid
        log("PROXY", f"PID={proxy_proc.pid}", "info")

        if wait_for_port(PROXY_PORT, timeout=8):
            log("PROXY", f"Listening on :{PROXY_PORT}", "ok")
        else:
            log("PROXY", "Proxy failed (non-fatal, external access only)", "warn")
    else:
        log("PROXY", "http_proxy.py not found, skipping", "warn")

    # 6. Save PIDs
    save_pids(pids)

    # 7. Health check
    print()
    log("CHECK", "Verifying health...", "info")

    for url, name in [
        (f"http://localhost:{BACKEND_PORT}/api/health", "Backend API"),
        (f"http://localhost:{VITE_PORT}/", "Frontend Vite"),
    ]:
        try:
            r = urllib.request.urlopen(url, timeout=5)
            log("CHECK", f"{name}: HTTP {r.status}", "ok")
        except Exception as e:
            log("CHECK", f"{name}: {str(e)[:60]}", "warn")

    # 8. Summary
    print()
    print("=" * 50)
    print("  PMON-AI-OPS  All Services Running!")
    print("=" * 50)
    print(f"""
  Frontend (browser):
    Local:    http://localhost:{VITE_PORT}
    LAN:      http://192.168.10.5:{VITE_PORT}
    External: https://22mj4798in35.vicp.fun

  Backend API:
    http://localhost:{BACKEND_PORT}
    http://localhost:{BACKEND_PORT}/docs  (Swagger)

  WebSocket:  ws://localhost:{BACKEND_PORT}/ws
  TFTP dir:   {tftp_dir}

  Logs:       {PROJECT_ROOT / "logs"}
  Stop:       python pmon.py stop
  Restart:    python pmon.py restart
""")


def cmd_stop():
    print("\n" + "=" * 50)
    print("  PMON-AI-OPS  Stopping Services")
    print("=" * 50 + "\n")

    # Kill by PID file first
    pids = load_pids()
    for name, pid in pids.items():
        try:
            if os.name == "nt":
                # On Windows, check with tasklist
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True, timeout=5,
                )
                if str(pid) in result.stdout:
                    kill_proc(pid)
                    log("STOP", f"{name} PID={pid}", "ok")
                else:
                    log("SKIP", f"{name} PID={pid} (not running)", "warn")
            else:
                os.kill(pid, 0)
                kill_proc(pid)
                log("STOP", f"{name} PID={pid}", "ok")
        except ProcessLookupError:
            log("SKIP", f"{name} PID={pid} (not running)", "warn")

    # Fallback: kill by port
    for port, name in [(BACKEND_PORT, "Backend"), (VITE_PORT, "Frontend"), (PROXY_PORT, "Proxy")]:
        if is_port_listening(port):
            kill_port(port)
            log("STOP", f"{name} on :{port}", "ok")

    # Clean PID file
    if PID_FILE.exists():
        PID_FILE.unlink()

    log("DONE", "All services stopped", "ok")
    print()


def cmd_status():
    print("\n  PMON-AI-OPS  Service Status")
    print("  " + "-" * 40)

    for port, name in [(BACKEND_PORT, "Backend"), (VITE_PORT, "Frontend"), (PROXY_PORT, "Proxy")]:
        if is_port_listening(port):
            log(name, f":{port}  RUNNING", "ok")
        else:
            log(name, f":{port}  STOPPED", "err")

    pids = load_pids()
    if pids:
        print(f"\n  PID file: {pids}")

    # Quick API check
    try:
        r = urllib.request.urlopen(f"http://localhost:{BACKEND_PORT}/api/health", timeout=3)
        log("API", f"Health: {r.read().decode()[:80]}", "ok")
    except Exception:
        log("API", "Not responding", "err")
    print()


def cmd_logs():
    log_dir = PROJECT_ROOT / "logs"
    if not log_dir.exists():
        log("ERR", "No logs directory. Start services first.", "err")
        return

    log("INFO", "Tailing logs (Ctrl+C to exit)...\n", "info")
    try:
        subprocess.run(
            ["powershell", "-Command",
             f"Get-Content '{log_dir}\\*.log' -Wait -Tail 50"],
        )
    except KeyboardInterrupt:
        print("\n  Stopped tailing logs.")


def cmd_restart():
    cmd_stop()
    time.sleep(2)
    cmd_start()


# ── Main ───────────────────────────────────────────────────────

COMMANDS = {
    "start": cmd_start,
    "stop": cmd_stop,
    "restart": cmd_restart,
    "status": cmd_status,
    "logs": cmd_logs,
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print("Available commands:", ", ".join(COMMANDS.keys()))
        sys.exit(1)

    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
