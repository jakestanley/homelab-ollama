import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psutil
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request, send_file


load_dotenv()

APP_ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.getenv("STATE_DIR", str(APP_ROOT / "data")))
STATE_FILE = STATE_DIR / "state.json"
JOBS_DIR = STATE_DIR / "jobs"

SERVICE_HOST = os.getenv("SERVICE_HOST", "127.0.0.1")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "5000"))

OLLAMA_EXE = os.getenv("OLLAMA_EXE", "ollama")
OLLAMA_ARGS = os.getenv("OLLAMA_ARGS", "serve")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))
DEFAULT_OLLAMA_PROCESS_NAME = "ollama.exe" if os.name == "nt" else "ollama"
OLLAMA_PROCESS_NAME = os.getenv("OLLAMA_PROCESS_NAME", DEFAULT_OLLAMA_PROCESS_NAME)
OLLAMA_MANAGED_BY_SERVICE = os.getenv("OLLAMA_MANAGED_BY_SERVICE", "0") not in {"0", "false", "False"}
OLLAMA_REQUIRE_SERVE = os.getenv("OLLAMA_REQUIRE_SERVE", "1") not in {"0", "false", "False"}
OLLAMA_STOP_SCOPE = os.getenv("OLLAMA_STOP_SCOPE", "all").lower()

STOP_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_STOP_TIMEOUT", "8"))

MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "50"))
JOBS_MAX_WORKERS = int(os.getenv("JOBS_MAX_WORKERS", "1"))

JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9._/:-]+$")


class OllamaUnavailable(RuntimeError):
    pass


class JobNotFound(KeyError):
    pass


app = Flask(__name__)


def _resolve_executable(exe: str) -> str | None:
    exe = (exe or "").strip()
    if not exe:
        return None

    p = Path(exe)
    if p.is_absolute() or ("\\" in exe) or ("/" in exe):
        return str(p) if p.exists() else None

    resolved = shutil.which(exe)
    return resolved

app.config["MAX_CONTENT_LENGTH"] = int(MAX_UPLOAD_MB * 1024 * 1024)


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


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
        "managed_by_service": OLLAMA_MANAGED_BY_SERVICE,
    }


def _ollama_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    if not env.get("HOME"):
        ensure_state_dir()
        env["HOME"] = str(STATE_DIR)
    return env


def _schedule_service_restart(delay_seconds: float = 0.2) -> None:
    def _exit_process() -> None:
        os._exit(1)

    timer = threading.Timer(delay_seconds, _exit_process)
    timer.daemon = True
    timer.start()


def start_ollama() -> dict:
    status = current_status()
    if OLLAMA_MANAGED_BY_SERVICE:
        return {
            "status": "service_managed",
            "message": "Ollama is managed by the service lifecycle. Start or restart the service instead.",
            **status,
        }

    if status["running"]:
        return {"status": "already_running", **status}

    resolved_exe = _resolve_executable(OLLAMA_EXE)
    if not resolved_exe:
        return {
            "status": "error",
            "error": f"Ollama executable not found: {OLLAMA_EXE}. "
            "Set OLLAMA_EXE in .env to a full path, especially when running as a Windows service.",
        }

    args = [resolved_exe] + shlex.split(OLLAMA_ARGS)
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
            env=_ollama_subprocess_env(),
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
    if OLLAMA_MANAGED_BY_SERVICE:
        return {
            "status": "service_managed",
            "message": "Ollama is managed by the service lifecycle. Stop the service to stop Ollama.",
            **status,
        }

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


def restart_ollama() -> dict:
    status = current_status()

    if OLLAMA_MANAGED_BY_SERVICE:
        write_state(
            {
                "last_action": "restart",
                "last_pid": status["pids"][0] if status["pids"] else None,
                "last_restarted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
        _schedule_service_restart()
        return {
            "status": "restarting",
            "message": "Service-managed restart requested. The service will reconnect after systemd restarts it.",
            **status,
        }

    was_running = status["running"]
    if was_running:
        stop_result = stop_ollama()
        if stop_result.get("running"):
            return {
                "status": "error",
                "message": "Failed to stop Ollama before restart.",
                **stop_result,
            }

    start_result = start_ollama()
    restart_status = "restarted" if was_running else start_result.get("status", "started")
    return {
        **start_result,
        "status": restart_status,
        "message": "Ollama restart requested.",
    }


def _atomic_write_json(path: Path, payload: dict) -> None:
    ensure_state_dir()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _job_dir(job_id: str) -> Path:
    if not JOB_ID_RE.fullmatch(job_id):
        raise ValueError("Invalid job id")
    return JOBS_DIR / job_id


def _job_paths(job_id: str) -> dict[str, Path]:
    root = _job_dir(job_id)
    return {
        "root": root,
        "meta": root / "job.json",
        "input": root / "input.jsonl",
        "output": root / "output.jsonl",
    }


def _read_job(job_id: str) -> dict:
    paths = _job_paths(job_id)
    if not paths["meta"].exists():
        raise JobNotFound(job_id)
    return json.loads(paths["meta"].read_text(encoding="utf-8"))


def _write_job(job_id: str, payload: dict) -> None:
    paths = _job_paths(job_id)
    paths["root"].mkdir(parents=True, exist_ok=True)
    _atomic_write_json(paths["meta"], payload)


def _ollama_url(path: str) -> str:
    path = path if path.startswith("/") else f"/{path}"
    return f"http://{OLLAMA_HOST}:{OLLAMA_PORT}{path}"


def _ollama_json(method: str, path: str, payload: dict | None = None, timeout: float = 30.0) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(_ollama_url(path), data=data, method=method.upper(), headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = str(exc)
        raise OllamaUnavailable(f"Ollama HTTP error: {exc.code} {body}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise OllamaUnavailable(f"Ollama unavailable at {_ollama_url('/')}: {exc}") from exc

    try:
        return json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise OllamaUnavailable(f"Invalid JSON from Ollama: {exc}") from exc


def list_cached_models() -> list[str]:
    payload = _ollama_json("GET", "/api/tags", timeout=8.0)
    models = []
    for item in payload.get("models", []):
        name = item.get("name")
        if isinstance(name, str) and name:
            models.append(name)
    return sorted(set(models))


def _pull_model_cli(model: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [_resolve_executable(OLLAMA_EXE) or OLLAMA_EXE, "pull", model],
            cwd=str(APP_ROOT),
            capture_output=True,
            text=True,
            timeout=60 * 60,
            env=_ollama_subprocess_env(),
        )
    except FileNotFoundError:
        return False, f"Ollama executable not found: {OLLAMA_EXE}"
    except subprocess.TimeoutExpired:
        return False, "Model pull timed out"
    except OSError as exc:
        return False, str(exc)

    output = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        return False, err or output or f"ollama pull exited {result.returncode}"
    return True, output or "ok"


def _coerce_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _validate_model(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("Missing model")
    if not MODEL_RE.fullmatch(value):
        raise ValueError("Invalid model name")
    return value


def _build_line_prompt(user_prompt: str, line_payload: object) -> str:
    return (
        "Instruction:\n"
        f"{user_prompt.strip()}\n\n"
        "Input JSON:\n"
        f"{json.dumps(line_payload, ensure_ascii=False)}\n\n"
        "Return your result. If returning JSON, return only JSON."
    )


class JobRunner:
    def __init__(self, max_workers: int) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, threading.Thread] = {}
        self._semaphore = threading.BoundedSemaphore(max(1, max_workers))

    def submit(self, job_id: str) -> None:
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        with self._lock:
            self._active[job_id] = thread
        thread.start()

    def _run_job(self, job_id: str) -> None:
        acquired = self._semaphore.acquire(timeout=0)
        if not acquired:
            meta = _read_job(job_id)
            meta["status"] = "queued"
            meta["message"] = "Waiting for a worker slot"
            _write_job(job_id, meta)
            self._semaphore.acquire()

        try:
            self._run_job_inner(job_id)
        finally:
            self._semaphore.release()
            with self._lock:
                self._active.pop(job_id, None)

    def _run_job_inner(self, job_id: str) -> None:
        paths = _job_paths(job_id)
        meta = _read_job(job_id)
        model = meta["model"]
        user_prompt = meta["prompt"]

        meta["status"] = "starting"
        meta["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        meta["message"] = "Starting"

        if not port_open(OLLAMA_HOST, OLLAMA_PORT):
            meta["status"] = "failed"
            meta["message"] = f"Ollama API not reachable at {OLLAMA_HOST}:{OLLAMA_PORT}. Start Ollama first."
            meta["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _write_job(job_id, meta)
            return
        _write_job(job_id, meta)

        if meta.get("auto_pull_model"):
            try:
                cached = list_cached_models()
            except OllamaUnavailable:
                cached = []
            if model not in cached:
                meta["status"] = "pulling_model"
                meta["message"] = f"Pulling model: {model}"
                _write_job(job_id, meta)
                ok, pull_message = _pull_model_cli(model)
                if not ok:
                    meta["status"] = "failed"
                    meta["message"] = pull_message
                    meta["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    _write_job(job_id, meta)
                    return

        meta["status"] = "running"
        meta["message"] = "Processing"
        _write_job(job_id, meta)

        processed = 0
        errors = 0
        total = int(meta.get("total_lines") or 0)

        paths["output"].write_text("", encoding="utf-8")

        last_flush = time.monotonic()
        flush_every_lines = 5

        try:
            with paths["input"].open("r", encoding="utf-8") as in_f, paths["output"].open(
                "a", encoding="utf-8"
            ) as out_f:
                for line_number, line in enumerate(in_f, start=1):
                    raw = line.rstrip("\n")
                    if not raw.strip():
                        continue

                    try:
                        line_payload = json.loads(raw)
                    except json.JSONDecodeError:
                        line_payload = {"_raw": raw, "_error": "invalid_json"}

                    prompt = _build_line_prompt(user_prompt, line_payload)

                    try:
                        resp = _ollama_json(
                            "POST",
                            "/api/generate",
                            payload={"model": model, "prompt": prompt, "stream": False},
                            timeout=120.0,
                        )
                        text = resp.get("response", "")
                        output_obj: dict[str, object] = {
                            "line": line_number,
                            "input": line_payload,
                            "model": model,
                            "output": text,
                        }
                        if isinstance(text, str):
                            candidate = text.strip()
                            if candidate.startswith("{") or candidate.startswith("["):
                                try:
                                    output_obj["output_json"] = json.loads(candidate)
                                except json.JSONDecodeError:
                                    pass
                    except OllamaUnavailable as exc:
                        errors += 1
                        output_obj = {
                            "line": line_number,
                            "input": line_payload,
                            "model": model,
                            "error": str(exc),
                        }
                    except Exception as exc:
                        errors += 1
                        output_obj = {
                            "line": line_number,
                            "input": line_payload,
                            "model": model,
                            "error": f"Unhandled error: {exc}",
                        }

                    out_f.write(json.dumps(output_obj, ensure_ascii=False) + "\n")
                    processed += 1

                    now = time.monotonic()
                    if processed % flush_every_lines == 0 or now - last_flush > 1.0:
                        meta = _read_job(job_id)
                        meta["processed_lines"] = processed
                        meta["error_lines"] = errors
                        meta["total_lines"] = total
                        meta["message"] = "Processing"
                        _write_job(job_id, meta)
                        last_flush = now

        except Exception as exc:
            meta = _read_job(job_id)
            meta["status"] = "failed"
            meta["message"] = f"Job failed: {exc}"
            meta["processed_lines"] = processed
            meta["error_lines"] = errors
            meta["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _write_job(job_id, meta)
            return

        meta = _read_job(job_id)
        meta["status"] = "completed"
        meta["processed_lines"] = processed
        meta["error_lines"] = errors
        meta["total_lines"] = total
        meta["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        meta["message"] = "Completed"
        _write_job(job_id, meta)


JOB_RUNNER = JobRunner(max_workers=JOBS_MAX_WORKERS)


@app.get("/api/status")
def api_status():
    return jsonify(current_status())


@app.post("/api/start")
def api_start():
    return jsonify(start_ollama())


@app.post("/api/stop")
def api_stop():
    return jsonify(stop_ollama())


@app.post("/api/restart")
def api_restart():
    return jsonify(restart_ollama())


@app.get("/api/models")
def api_models():
    try:
        models = list_cached_models()
    except OllamaUnavailable as exc:
        return jsonify({"models": [], "error": str(exc)}), 503
    return jsonify({"models": models})


@app.post("/api/jobs")
def api_jobs_create():
    if "file" not in request.files:
        return jsonify({"error": "Missing file field 'file'"}), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"error": "Missing filename"}), 400

    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "Missing prompt"}), 400

    try:
        model = _validate_model(request.form.get("model") or "")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    auto_pull_model = _coerce_bool(request.form.get("auto_pull_model"), default=True)

    job_id = uuid.uuid4().hex
    paths = _job_paths(job_id)
    paths["root"].mkdir(parents=True, exist_ok=True)

    total_lines = 0

    try:
        with paths["input"].open("w", encoding="utf-8") as f:
            for raw_line in upload.stream:
                text = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, (bytes, bytearray)) else str(raw_line)
                f.write(text)
                total_lines += 1
    except OSError as exc:
        return jsonify({"error": str(exc)}), 500

    meta = {
        "id": job_id,
        "status": "queued",
        "message": "Queued",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "started_at": None,
        "finished_at": None,
        "model": model,
        "prompt": prompt,
        "auto_pull_model": auto_pull_model,
        "total_lines": total_lines,
        "processed_lines": 0,
        "error_lines": 0,
    }

    _write_job(job_id, meta)
    JOB_RUNNER.submit(job_id)
    return jsonify({"id": job_id})


@app.get("/api/jobs/<job_id>")
def api_jobs_get(job_id: str):
    try:
        meta = _read_job(job_id)
    except (ValueError, JobNotFound, json.JSONDecodeError):
        abort(404)
    return jsonify(meta)


@app.get("/api/jobs/<job_id>/output")
def api_jobs_output(job_id: str):
    try:
        paths = _job_paths(job_id)
    except ValueError:
        abort(404)
    if not paths["output"].exists():
        abort(404)

    return send_file(
        paths["output"],
        mimetype="application/jsonl",
        as_attachment=True,
        download_name="output.jsonl",
    )


@app.get("/")
def index():
    return render_template("index.html")


def main() -> int:
    ensure_state_dir()
    app.run(host=SERVICE_HOST, port=SERVICE_PORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
