# Recovery

## Prerequisites

- Windows host with Ollama installed and available on PATH (or set `OLLAMA_EXE`).
- Python 3.11+ installed.
- `homelab-infra` and `homelab-standards` sibling repositories present.

## Recovery order

1. Confirm `homelab-infra/registry.yaml` still defines the service port.
2. Verify `.env` values, especially `SERVICE_PORT` and `OLLAMA_EXE`.
3. Restart the NSSM service for `homelab-ollama`.
4. Validate `GET /api/status` reports `running: true` when Ollama is expected up.

## Do not change casually

- Service port or ingress settings (defined in `homelab-infra`).
- Ollama runtime port unless explicitly required.
- NSSM service name or install directory without updating recovery docs.
