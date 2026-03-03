#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
DEFAULT_VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"
DEFAULT_VENV_PYTHON3="${ROOT_DIR}/.venv/bin/python3"
APP_PID=""
OLLAMA_PID=""
SHUTTING_DOWN=0

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

is_true() {
  local value="${1:-}"
  case "${value}" in
    1|true|TRUE|True|yes|YES|Yes|on|ON|On) return 0 ;;
    *) return 1 ;;
  esac
}

resolve_executable() {
  local exe="${1:-}"
  if [[ -z "${exe}" ]]; then
    return 1
  fi

  if [[ "${exe}" == */* ]]; then
    [[ -x "${exe}" ]] || return 1
    printf '%s\n' "${exe}"
    return 0
  fi

  command -v "${exe}" 2>/dev/null || return 1
}

terminate_child() {
  local pid="${1:-}"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill -TERM "${pid}" 2>/dev/null || true
  fi
}

wait_child() {
  local pid="${1:-}"
  if [[ -n "${pid}" ]]; then
    wait "${pid}" 2>/dev/null || true
  fi
}

shutdown_children() {
  SHUTTING_DOWN=1
  terminate_child "${APP_PID}"
  terminate_child "${OLLAMA_PID}"
  wait_child "${APP_PID}"
  wait_child "${OLLAMA_PID}"
}

if ! is_true "${OLLAMA_MANAGED_BY_SERVICE:-0}"; then
  exec "${python_bin}" "${ROOT_DIR}/app.py"
fi

resolved_ollama_exe="$(resolve_executable "${OLLAMA_EXE:-ollama}" || true)"
if [[ -z "${resolved_ollama_exe}" ]]; then
  echo "Ollama executable not found or not executable: ${OLLAMA_EXE:-ollama}" >&2
  exit 1
fi

trap 'shutdown_children; exit 0' TERM INT
trap 'shutdown_children' EXIT

read -r -a ollama_args <<< "${OLLAMA_ARGS:-serve}"
"${resolved_ollama_exe}" "${ollama_args[@]}" &
OLLAMA_PID=$!

sleep 1
if ! kill -0 "${OLLAMA_PID}" 2>/dev/null; then
  wait "${OLLAMA_PID}"
  exit $?
fi

"${python_bin}" "${ROOT_DIR}/app.py" &
APP_PID=$!

while true; do
  if ! kill -0 "${OLLAMA_PID}" 2>/dev/null; then
    wait "${OLLAMA_PID}" || child_status=$?
    child_status="${child_status:-1}"
    echo "ollama serve exited while the service was active" >&2
    break
  fi

  if ! kill -0 "${APP_PID}" 2>/dev/null; then
    wait "${APP_PID}" || child_status=$?
    child_status="${child_status:-1}"
    echo "app.py exited while the service was active" >&2
    break
  fi

  sleep 1
done

shutdown_children
trap - EXIT

if [[ "${SHUTTING_DOWN}" -eq 1 ]]; then
  if [[ "${child_status:-1}" -eq 0 ]]; then
    exit 1
  fi
  exit "${child_status:-1}"
fi
