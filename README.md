# homelab-ollama

Windows service wrapper for a locally installed Ollama runtime.
It exposes a minimal HTTP API and UI to start, stop, and query status.

Canonical standards live in the sibling repository `homelab-standards`.

## Runtime

- Host: Windows
- Runtime: Python + NSSM (no Docker)
- Ports and ingress are defined in `homelab-infra/registry.yaml`

## API

### Runtime control

- `GET /api/status` -> running state + PIDs
- `POST /api/start` -> start Ollama (idempotent)
- `POST /api/stop` -> stop Ollama (idempotent)

### Models

- `GET /api/models` -> list cached models (via Ollama `GET /api/tags`)

### JSONL batch jobs

- `POST /api/jobs` (multipart form)
  - fields: `file` (JSONL), `prompt` (text), `model` (text), `auto_pull_model` (`1`/`0`, default `1`)
  - returns: `{ "id": "..." }`
- `GET /api/jobs/<id>` -> job status/metadata
- `GET /api/jobs/<id>/output` -> download processed `output.jsonl`

Output format: one JSON object per processed input line, containing at least:
`line`, `input`, `model`, and either `output` or `error`.

Job state is stored under `STATE_DIR/jobs/<id>/`.

## UI

Visit `/` to view the control panel and JSONL batch processor.

## Setup

1. Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and set `SERVICE_PORT` to the registry value.

3. Run locally:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

Or use the helper script:

```powershell
.\scripts\up.ps1
```

## NSSM service example

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

## Notes

- If Ollama is installed via Scoop or user PATH, NSSM running as LocalSystem may not find it; set `OLLAMA_EXE` to a full path or run the service as your user.
- Ollama listens on its own port (default `11434`); this service only controls the local process and proxies nothing.
- JSONL jobs call the local Ollama HTTP API per line; keep prompts concise for performance.
- `MAX_UPLOAD_MB` limits upload size and `JOBS_MAX_WORKERS` limits concurrency.
