import json
import os
import shlex
import socket
import subprocess
import time
from pathlib import Path

import psutil
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template


load_dotenv()

APP_ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.getenv("STATE_DIR", str(APP_ROOT / "data")))
STATE_FILE = STATE_DIR / "state.json"

SERVICE_HOST = os.getenv("SERVICE_HOST", "127.0.0.1")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "5000"))

OLLAMA_EXE = os.getenv("OLLAMA_EXE", "ollama")
OLLAMA_ARGS = os.getenv("OLLAMA_ARGS", "serve")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))
OLLAMA_PROCESS_NAME = os.getenv("OLLAMA_PROCESS_NAME", "ollama.exe")
OLLAMA_REQUIRE_SERVE = os.getenv("OLLAMA_REQUIRE_SERVE", "1") not in {"0", "false", "False"}
OLLAMA_STOP_SCOPE = os.getenv("OLLAMA_STOP_SCOPE", "all").lower()

STOP_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_STOP_TIMEOUT", "8"))

app = Flask(__name__)


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(data: dict) -> None:
    ensure_state_dir()
    tmp_path = STATE_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp_path.replace(STATE_FILE)


def _is_serve_cmd(cmdline: list[str]) -> bool:
    for arg in cmdline:
        value = arg.lower()
        if value == "serve" or value.endswith("\\serve") or value.endswith("/serve"):
            return True
    return False


def list_ollama_processes() -> list[psutil.Process]:
    matches = []
    name_match = OLLAMA_PROCESS_NAME.lower()
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            info = proc.info
            proc_name = (info.get("name") or "").lower()
            proc_exe = (Path(info["exe"]).name.lower() if info.get("exe") else "")
            if name_match not in {proc_name, proc_exe}:
                continue
            cmdline = info.get("cmdline") or []
            if OLLAMA_REQUIRE_SERVE and cmdline and not _is_serve_cmd(cmdline):
                continue
            matches.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matches


def port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def current_status() -> dict:
    processes = list_ollama_processes()
    process_running = bool(processes)
    port_reachable = port_open(OLLAMA_HOST, OLLAMA_PORT)
    return {
        "running": process_running or port_reachable,
        "process_running": process_running,
        "port_open": port_reachable,
        "pids": [proc.pid for proc in processes],
        "ollama_host": OLLAMA_HOST,
        "ollama_port": OLLAMA_PORT,
    }


def start_ollama() -> dict:
    status = current_status()
    if status["running"]:
        return {"status": "already_running", **status}

    args = [OLLAMA_EXE] + shlex.split(OLLAMA_ARGS)
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    try:
        proc = subprocess.Popen(
            args,
            cwd=str(APP_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    except FileNotFoundError:
        return {"status": "error", "error": f"Ollama executable not found: {OLLAMA_EXE}"}
    except OSError as exc:
        return {"status": "error", "error": str(exc)}

    write_state(
        {
            "last_action": "start",
            "last_pid": proc.pid,
            "last_started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )

    time.sleep(0.6)
    status = current_status()
    return {"status": "started", **status}


def stop_ollama() -> dict:
    status = current_status()
    if not status["running"]:
        return {"status": "already_stopped", **status}

    processes = list_ollama_processes()
    if OLLAMA_STOP_SCOPE == "pidfile":
        state = read_state()
        pid = state.get("last_pid")
        processes = [proc for proc in processes if proc.pid == pid]

    for proc in processes:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    _, alive = psutil.wait_procs(processes, timeout=STOP_TIMEOUT_SECONDS)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    write_state(
        {
            "last_action": "stop",
            "last_pid": status["pids"][0] if status["pids"] else None,
            "last_stopped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )

    time.sleep(0.4)
    status = current_status()
    return {"status": "stopped", **status}


@app.get("/api/status")
def api_status():
    return jsonify(current_status())


@app.post("/api/start")
def api_start():
    return jsonify(start_ollama())


@app.post("/api/stop")
def api_stop():
    return jsonify(stop_ollama())


@app.get("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    ensure_state_dir()
    app.run(host=SERVICE_HOST, port=SERVICE_PORT)
