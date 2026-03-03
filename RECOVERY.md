# Recovery

## Prerequisites

- Linux host with `systemd`, `journalctl`, Python 3.11+, and Ollama installed
- Windows host with Ollama installed and available on PATH, or `OLLAMA_EXE` set explicitly
- Python 3.11+ installed
- `homelab-infra` and `homelab-standards` sibling repositories present
- Linux service user/group present:
  - user: `homelab-ollama`
  - group: `homelab-ollama`

Dependency checks:

- `systemctl --version`
- `systemd-analyze --version`
- `journalctl --version`
- `python3 --version`
- `command -v ollama`

## Recovery order

1. Confirm `homelab-infra/registry.yaml` still defines the service identity and service port.
2. Restore the repo checkout under `/srv/homelab-ollama`, including `app.py`, `templates/`, `scripts/`, and `systemd/`.
3. Restore the Linux unit file to `/etc/systemd/system/homelab-ollama.service`.
4. Restore the Linux host env file to `/etc/homelab-ollama/homelab-ollama.env`.
5. Restore writable state at the configured `STATE_DIR`, typically `/var/lib/homelab-ollama`.
6. Verify ownership of the repo checkout and writable state for the `homelab-ollama` service user/group.
7. Verify env values, especially `SERVICE_PORT`, `PYTHON_BIN`, `OLLAMA_EXE`, and `STATE_DIR`.
8. Run `sudo systemctl daemon-reload`.
9. Run `sudo systemctl enable --now homelab-ollama.service`.
10. Verify with `systemctl status homelab-ollama.service`, `journalctl -u homelab-ollama.service -n 50`, and `GET /api/status`.

Windows recovery remains:

1. Verify `.env` values, especially `SERVICE_PORT` and `OLLAMA_EXE`.
2. Restart the NSSM service for `homelab-ollama`.
3. Validate `GET /api/status` reports `running: true` when Ollama is expected up.

## Verification steps

- Verify service user/group:
  - `getent passwd homelab-ollama`
  - `getent group homelab-ollama`
- Verify the configured interpreter:
  - `test -x "$(awk -F= '/^PYTHON_BIN=/{print $2}' /etc/homelab-ollama/homelab-ollama.env)"`
- Verify the unit file is installed:
  - `test -f /etc/systemd/system/homelab-ollama.service`
- Verify the host env file is installed:
  - `test -f /etc/homelab-ollama/homelab-ollama.env`
- Verify writable state path ownership:
  - `stat /var/lib/homelab-ollama`

## Do not change casually

- Service port or ingress settings managed in `homelab-infra`
- Ollama runtime port unless explicitly required
- NSSM service name or install directory without updating the docs
- Linux unit path, service user/group, or `STATE_DIR` without updating the systemd env file and docs
