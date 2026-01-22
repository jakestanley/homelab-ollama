# homelab-ollama

Windows service wrapper for a locally installed Ollama runtime.
It exposes a minimal HTTP API and UI to start, stop, and query status.

Canonical standards live in the sibling repository `homelab-standards`.

## Runtime

- Host: Windows
- Runtime: Python + NSSM (no Docker)
- Ports and ingress are defined in `homelab-infra/registry.yaml`

## API

- `GET /api/status` -> running state + PIDs
- `POST /api/start` -> start Ollama (idempotent)
- `POST /api/stop` -> stop Ollama (idempotent)

## UI

Visit `/` to view the control panel and status.

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

- This service does not manage Ollama models or authentication.
- Ollama listens on its own port (default `11434`); this service only controls
  the local process.
