# AGENTS.md

Canonical agent behaviour and standards are defined in:

https://github.com/jakestanley/homelab-standards/blob/main/AGENTS.md

Vendored copies may exist under `imported/` for tool visibility.

## Stability contract

Two consumers depend on this repo's surface and must keep working:

1. **Docker Compose** — `docker-compose.yml` + `Dockerfile`. Note that
   compose runs both `ollama` (the official image) and this app; the
   compose env block hardcodes inter-container networking and is
   deliberately different from `.env.example`.
2. **Ansible NSSM deployment** in `jakestanley/windows` (the `shrike` repo).
   Its `ansible/roles/services/tasks/main.yml` clones this repo into
   `C:\homelab\homelab-ollama\`, seeds `.env` from `.env.example`, and runs
   `scripts/up.ps1`. On Windows the Ollama runtime is installed separately;
   only the Flask app becomes the NSSM service.

Do not rename, move, or remove the following without a paired PR to both
consumers:

- `docker-compose.yml`, `Dockerfile`, `requirements.txt`
- `.env.example` — the single canonical config template for compose
  (the keys read from it) and NSSM
- `scripts/up.ps1` — idempotent NSSM install / update / start; accepts
  `-Restart`
- `scripts/uninstall.ps1`

Reserved env keys in `.env.example`:

- `OLLAMA_PYTHON_EXE` — matches shrike's `^([A-Z_]+_PYTHON_EXE)=` seed
  pattern and is rewritten to the discovered `python.exe` path on first
  clone. Renaming this key breaks auto-seeding.
- `OLLAMA_EXE` — also rewritten by shrike's seed task to the discovered
  `ollama.exe` path when Ollama is installed at clone time.
- `SERVICE_PORT` — declared port used by the firewall rule in `up.ps1`.
- `DATA_DIR` — host bind path for the compose volume; not used in NSSM
  mode (NSSM uses `STATE_DIR` instead).
- `NSSM_SERVICE_NAME`, `NSSM_DISPLAY_NAME`, `NSSM_DESCRIPTION` — namespace
  reserved for NSSM service identity. Filtered out of `AppEnvironmentExtra`
  before being passed to the app process.

The compose-vs-NSSM env split is deliberate: compose uses docker DNS
(`OLLAMA_HOST=ollama`), NSSM uses localhost (`OLLAMA_HOST=127.0.0.1`).
Don't try to unify them.
