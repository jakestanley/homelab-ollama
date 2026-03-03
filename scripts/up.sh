#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
DEFAULT_VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"
DEFAULT_VENV_PYTHON3="${ROOT_DIR}/.venv/bin/python3"

if [[ -f "${ENV_FILE}" && -z "${INVOCATION_ID:-}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [[ -n "${PYTHON_BIN:-}" ]]; then
  python_bin="${PYTHON_BIN}"
elif [[ -x "${DEFAULT_VENV_PYTHON}" ]]; then
  python_bin="${DEFAULT_VENV_PYTHON}"
elif [[ -x "${DEFAULT_VENV_PYTHON3}" ]]; then
  python_bin="${DEFAULT_VENV_PYTHON3}"
else
  python_bin="$(command -v python3 || true)"
fi

if [[ -z "${python_bin:-}" ]]; then
  echo "python3 not found. Set PYTHON_BIN to an absolute interpreter path." >&2
  exit 1
fi

if [[ ! -x "${python_bin}" ]]; then
  echo "Configured PYTHON_BIN is not executable: ${python_bin}" >&2
  exit 1
fi

exec "${python_bin}" "${ROOT_DIR}/app.py"
