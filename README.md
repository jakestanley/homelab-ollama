# homelab-ollama

Host service wrapper for a locally installed Ollama runtime. It exposes a
minimal HTTP API and UI to query status and run JSONL batch jobs against the
local Ollama HTTP API. In Linux systemd installs, `ollama serve` is part of the
service lifecycle and is kept running while the service is active.

Canonical standards live in the sibling repository `homelab-standards`.

## Runtime

- Hosts: Windows and Linux
- Runtime: Python host service
- Windows service model: NSSM via `scripts/install-service.ps1`
- Linux service model: systemd via `scripts/up.sh` and `systemd/homelab-ollama.service`
- Ingress, ports, and exposure are managed in `homelab-infra`

The canonical generic Linux entrypoint is `scripts/up.sh`. It runs the app with
an explicit interpreter path and does not rely on shell startup files or
virtualenv activation side effects. When `OLLAMA_MANAGED_BY_SERVICE=1`,
`scripts/up.sh` supervises both the Flask app and `ollama serve`, and the unit
fails if either process exits unexpectedly. If `HOME` is unset in the service
environment, the wrapper defaults it to `STATE_DIR` so Ollama CLI operations can
resolve their writable runtime paths.

Mutable state is controlled by `STATE_DIR`, so Linux host installs and future
packaged deployments can keep writable state outside the repo checkout.

## API

### Runtime control

- `GET /api/status` -> running state + PIDs
- `POST /api/restart` -> restart Ollama; in service-managed mode this restarts the surrounding service so `ollama serve` and the web app come back together
- `POST /api/start` -> start Ollama when API-controlled; returns `service_managed` when the service owns the runtime
- `POST /api/stop` -> stop Ollama when API-controlled; returns `service_managed` when the service owns the runtime

### Models

- `GET /api/models` -> list cached models (via Ollama `GET /api/tags`)

### JSONL batch jobs

- `POST /api/jobs` (multipart form)
  - fields: `file` (JSONL), `prompt` (text), `model` (text), `auto_pull_model` (`1`/`0`, default `1`)
  - returns: `{ "id": "..." }`
- `GET /api/jobs/<id>` -> job status/metadata
- `GET /api/jobs/<id>/output` -> download processed `output.jsonl`

Output format: one JSON object per processed input line, containing at least
`line`, `input`, `model`, and either `output` or `error`.

Job state is stored under `STATE_DIR/jobs/<id>/`.

## UI

Visit `/` to view the control panel and JSONL batch processor. The web UI exposes
status, restart, and job controls; it does not expose separate start/stop
buttons.

## Dependencies

Required runtime dependencies:

- `systemd` on Linux
  - verify: `systemctl --version && systemd-analyze --version`
- Python 3.11+
  - verify: `python3 --version`
- Python packages from `requirements.txt`
  - verify after install: `python3 -c "import flask, psutil, dotenv"`
- `ollama`
  - verify on Linux: `command -v ollama`
  - verify on Windows: `Get-Command ollama.exe`

The executable referenced by the Linux unit comes from `PYTHON_BIN` in
`/etc/homelab-ollama/homelab-ollama.env`. Verify it with:

```sh
test -x /absolute/path/to/python
```

## Manual setup

Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./scripts/up.sh
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
.\scripts\up.ps1
```

Set `SERVICE_PORT` in `.env` to the value managed in `homelab-infra`. For Linux
systemd installs, also set an absolute `STATE_DIR` and, if needed, `PYTHON_BIN`
and `OLLAMA_EXE`. Leave `OLLAMA_MANAGED_BY_SERVICE=0` for local/manual runs
unless you explicitly want `scripts/up.sh` to supervise `ollama serve`.

## Linux systemd install

This repo ships:

- Unit template: `systemd/homelab-ollama.service`
- Host env template: `systemd/homelab-ollama.env.example`
- Canonical entrypoint: `scripts/up.sh`

Recommended install layout:

- Repo checkout: `/srv/homelab-ollama`
- Unit file: `/etc/systemd/system/homelab-ollama.service`
- Host env file: `/etc/homelab-ollama/homelab-ollama.env`
- Writable state: `/var/lib/homelab-ollama`
- Service user/group: `homelab-ollama`

1. Create the dedicated service account and writable directories:

```sh
sudo groupadd --system homelab-ollama
sudo useradd --system --gid homelab-ollama --home-dir /srv/homelab-ollama --shell /usr/sbin/nologin homelab-ollama
sudo install -d -o homelab-ollama -g homelab-ollama /etc/homelab-ollama /var/lib/homelab-ollama
```

2. Install Python dependencies in a stable interpreter location:

```sh
cd /srv/homelab-ollama
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

3. Install the host env file and set host-specific values:

```sh
sudo cp /srv/homelab-ollama/systemd/homelab-ollama.env.example /etc/homelab-ollama/homelab-ollama.env
sudo editor /etc/homelab-ollama/homelab-ollama.env
```

The shipped systemd env template sets `OLLAMA_MANAGED_BY_SERVICE=1`, so
`ollama serve` is started and monitored by the unit itself. Stopping the unit
stops Ollama; if `ollama serve` exits unexpectedly, the unit fails and
systemd restart policy applies.

4. Install and start the unit:

```sh
sudo cp /srv/homelab-ollama/systemd/homelab-ollama.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-ollama.service
```

5. View logs:

```sh
journalctl -u homelab-ollama.service -f
```

## Windows NSSM service

Preferred installation/update helper:

```powershell
.\scripts\install-service.ps1 -Start
```

Manual NSSM example:

```powershell
nssm install homelab-ollama "C:\\Path\\To\\python.exe" "C:\\Path\\To\\homelab-ollama\\app.py"
nssm set homelab-ollama AppDirectory "C:\\Path\\To\\homelab-ollama"
nssm set homelab-ollama AppEnvironmentExtra "PYTHONPATH=C:\\Path\\To\\homelab-ollama"
```

Use the NSSM GUI or `nssm set` to provide the `.env` variables and confirm the
service port matches `homelab-infra/registry.yaml`.

## Config files

- Repo env template: `.env.example`
- Local manual-run env file: `.env`
- Linux host env template: `systemd/homelab-ollama.env.example`
- Linux host env file: `/etc/homelab-ollama/homelab-ollama.env`

Key env vars:

- `SERVICE_HOST`
- `SERVICE_PORT`
- `PYTHON_BIN`
- `OLLAMA_EXE`
- `OLLAMA_MANAGED_BY_SERVICE`
- `OLLAMA_PROCESS_NAME`
- `STATE_DIR`
- `MAX_UPLOAD_MB`
- `JOBS_MAX_WORKERS`

## Notes

- On Linux, the default Ollama process name is `ollama`; on Windows it remains `ollama.exe`.
- For Linux systemd installs, `OLLAMA_MANAGED_BY_SERVICE=1` is the intended mode so the service and `ollama serve` share one lifecycle.
- If Ollama is installed via Scoop or user PATH, NSSM running as LocalSystem may not find it; set `OLLAMA_EXE` to a full path or run the service as your user.
- Ollama listens on its own port (default `11434`); this service only controls the local process and proxies nothing.
- JSONL jobs call the local Ollama HTTP API per line; keep prompts concise for performance.
- `MAX_UPLOAD_MB` limits upload size and `JOBS_MAX_WORKERS` limits concurrency.
