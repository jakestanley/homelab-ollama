#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STANDARDS_DIR="${ROOT_DIR}/../homelab-standards"
INFRA_DIR="${ROOT_DIR}/../homelab-infra"

CHECK_DEPS_SH="${STANDARDS_DIR}/scripts/check-deps.sh"
CHECK_IMPORTS_SH="${STANDARDS_DIR}/scripts/check-imports.sh"
SYNC_IMPORTS_SH="${STANDARDS_DIR}/scripts/sync-imports.sh"

confirm() {
  local prompt="$1"
  local answer=""

  if [[ -t 0 ]]; then
    read -r -p "${prompt}" answer || true
  else
    echo "${prompt}" >&2
    echo "Non-interactive session; refusing by default." >&2
    return 1
  fi

  case "${answer}" in
    y|Y|yes|YES|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

preflight_failed=0

if [[ ! -d "${STANDARDS_DIR}" ]]; then
  echo "Missing sibling repo: ${STANDARDS_DIR}" >&2
  preflight_failed=1
fi

if [[ ! -d "${INFRA_DIR}" ]]; then
  echo "Missing sibling repo: ${INFRA_DIR}" >&2
  preflight_failed=1
fi

if [[ -d "${STANDARDS_DIR}" ]]; then
  if [[ ! -f "${CHECK_DEPS_SH}" ]]; then
    echo "Missing file: ${CHECK_DEPS_SH}" >&2
    preflight_failed=1
  fi

  if [[ ! -f "${CHECK_IMPORTS_SH}" ]]; then
    echo "Missing file: ${CHECK_IMPORTS_SH}" >&2
    preflight_failed=1
  fi

  if [[ -f "${CHECK_DEPS_SH}" ]]; then
    if ! (cd "${STANDARDS_DIR}" && bash "scripts/check-deps.sh"); then
      preflight_failed=1
    fi
  fi
fi

mkdir -p "${ROOT_DIR}/imported"

sync_imports_missing=0

if [[ -f "${SYNC_IMPORTS_SH}" ]]; then
  (cd "${STANDARDS_DIR}" && bash "scripts/sync-imports.sh")
else
  echo "Missing file: ${SYNC_IMPORTS_SH}" >&2
  sync_imports_missing=1
fi

if [[ -d "${STANDARDS_DIR}" ]]; then
  if [[ -f "${CHECK_IMPORTS_SH}" ]]; then
    if ! (cd "${STANDARDS_DIR}" && bash "scripts/check-imports.sh"); then
      preflight_failed=1
    fi
  fi
fi

if [[ "${preflight_failed}" -ne 0 ]]; then
  if ! confirm "Preflight checks failed. Continue anyway? [y/N] "; then
    exit 1
  fi
fi

if [[ "${sync_imports_missing}" -ne 0 ]]; then
  if ! confirm "Continue without syncing imports? [y/N] "; then
    exit 1
  fi
fi

has_compose_services() {
  [[ -f "${ROOT_DIR}/docker-compose.yml" ]] || return 1
  awk '
    /^[[:space:]]*#/ { next }
    /^services:[[:space:]]*\{[[:space:]]*\}[[:space:]]*$/ { exit 1 }
    /^services:[[:space:]]*$/ { in_services=1; next }
    in_services && /^[^[:space:]]/ { in_services=0 }
    in_services && /^[[:space:]]{2}[A-Za-z0-9_.-]+:[[:space:]]*$/ { found=1; exit 0 }
    END { exit(found ? 0 : 1) }
  ' "${ROOT_DIR}/docker-compose.yml"
}

if has_compose_services; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found; cannot run docker compose." >&2
    exit 1
  fi

  (cd "${ROOT_DIR}" && docker compose up -d)
else
  echo "No runtime is defined yet (docker-compose.yml has no services)."
fi
