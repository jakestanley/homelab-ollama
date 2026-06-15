# homelab-ollama

Minimal HTTP API and UI to run JSONL batch jobs against a local Ollama runtime.
Ingress, ports, and exposure are managed in the sibling repository `homelab-infra`.

## Deployment

### Docker Compose (Linux, primary)

```sh
docker compose up -d --build
```

This starts two services:

- `ollama` — the official Ollama image with GPU passthrough and a persistent model volume
- `homelab-ollama` — the Flask app, listening on port `20030`

The app connects to Ollama over the Docker network. No `.env` file is required.

To override the host path for job state (default `/var/lib/homelab-ollama`):

```sh
DATA_DIR=/your/path docker compose up -d --build
```

### Windows NSSM service (secondary)

`scripts/up.ps1` is the single idempotent entrypoint for service creation,
updating, and starting. It creates the venv, installs requirements, ensures
the Windows Firewall rule, and applies the NSSM service config.

1. Copy and configure the env file:

```powershell
Copy-Item .env.example .env
# Edit .env: set SERVICE_PORT, OLLAMA_PYTHON_EXE, and OLLAMA_EXE as needed.
```

2. Install / update / start (elevated PowerShell):

```powershell
.\scripts\up.ps1
```

Force restart if already running:

```powershell
.\scripts\up.ps1 -Restart
```

Uninstall:

```powershell
.\scripts\uninstall.ps1
```

Ollama must be installed and running separately on Windows. The app expects it at
`OLLAMA_HOST:OLLAMA_PORT` (default `127.0.0.1:11434`).

## API

### Models

- `GET /api/models` — list cached models

### JSONL batch jobs

- `POST /api/jobs` (multipart form)
  - fields: `file` (JSONL), `prompt` (text), `model` (text), `auto_pull_model` (`1`/`0`, default `1`)
  - returns: `{ "id": "..." }`
- `GET /api/jobs/<id>` — job status and metadata
- `GET /api/jobs/<id>/output` — download `output.jsonl`

Output format: one JSON object per input line with `line`, `input`, `model`, and either `output` or `error`.

Job state is stored under `STATE_DIR/jobs/<id>/`.

## UI

Visit `/` for the control panel and JSONL batch processor.

## Config

Docker Compose app vars are hardcoded in `docker-compose.yml`. Only `DATA_DIR` is read from the environment (or `.env`) to set the host volume mount path.

The Windows NSSM service reads all vars from `.env`.

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `/var/lib/homelab-ollama` | Host path for job state (Docker Compose only) |
| `SERVICE_PORT` | `20030` | Port to listen on (both modes; must match homelab-infra/registry.yaml) |
| `SERVICE_HOST` | `127.0.0.1` | Interface to listen on |
| `OLLAMA_PYTHON_EXE` | _(none)_ | Absolute Python path for `scripts/up.ps1` venv bootstrap |
| `OLLAMA_HOST` | `127.0.0.1` | Ollama host |
| `OLLAMA_PORT` | `11434` | Ollama port |
| `OLLAMA_EXE` | `ollama` | Ollama executable (Windows; prefer full path under NSSM) |
| `STATE_DIR` | `data` | Path for job state storage (NSSM) / `/data` (Docker Compose) |
| `MAX_UPLOAD_MB` | `50` | Max JSONL upload size |
| `JOBS_MAX_WORKERS` | `1` | Max concurrent jobs |
| `NSSM_SERVICE_NAME` | `homelab-ollama` | Optional NSSM service name override |
| `NSSM_DISPLAY_NAME` | `homelab-ollama` | Optional NSSM display name |
| `NSSM_DESCRIPTION` | _(default text)_ | Optional NSSM description |

## Notes

- JSONL jobs pull models via the Ollama HTTP API (`POST /api/pull`) when `auto_pull_model=1`.
- If Ollama is installed via Scoop or user PATH, NSSM running as LocalSystem may not find it; set `OLLAMA_EXE` to a full path or run the service as your user.
