#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"
RUN_DIR="${PROJECT_ROOT}/data/run"
LOG_DIR="${PROJECT_ROOT}/data/logs"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"

mkdir -p "${RUN_DIR}" "${LOG_DIR}"

info() {
    printf '[INFO] %s\n' "$*"
}

warn() {
    printf '[WARN] %s\n' "$*" >&2
}

error() {
    printf '[ERROR] %s\n' "$*" >&2
}

load_nvm_if_available() {
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [ -s "${NVM_DIR}/nvm.sh" ]; then
        # shellcheck source=/dev/null
        . "${NVM_DIR}/nvm.sh"
    fi
}

ensure_backend_env() {
    if [ ! -d "${INDEX_TTS_DIR}/.venv" ]; then
        error "未找到 index-tts 虚拟环境: ${INDEX_TTS_DIR}/.venv"
        error "请先完成环境安装。"
        exit 1
    fi

    export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
    export HF_HOME="${INDEX_TTS_DIR}/.cache/hf"
    export HF_HUB_CACHE="${HF_HOME}"
    export TRANSFORMERS_CACHE="${HF_HOME}"
    export PYTHONUNBUFFERED=1
    export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
    export PYTHONPATH="${PROJECT_ROOT}/index-tts:${PYTHONPATH:-}"

    local nvidia_cudnn_dir="${INDEX_TTS_DIR}/.venv/lib/python3.10/site-packages/nvidia/cudnn/lib"
    if [ -d "${nvidia_cudnn_dir}" ]; then
        export LD_LIBRARY_PATH="${nvidia_cudnn_dir}:${LD_LIBRARY_PATH:-}"
    fi
}

ensure_frontend_env() {
    load_nvm_if_available

    if ! command -v node >/dev/null 2>&1; then
        error "未找到 Node.js，请先安装 Node.js 20+。"
        exit 1
    fi

    if [ ! -d "${PROJECT_ROOT}/frontend/node_modules" ]; then
        error "未找到 frontend/node_modules，请先安装前端依赖。"
        exit 1
    fi
}

pid_file_for() {
    printf '%s/%s.pid' "${RUN_DIR}" "$1"
}

log_file_for() {
    printf '%s/%s.log' "${LOG_DIR}" "$1"
}

is_pid_running() {
    local pid="$1"
    [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null
}

read_pid() {
    local file="$1"
    if [ -f "${file}" ]; then
        tr -d '[:space:]' < "${file}"
    fi
}

remove_pid_file_if_stale() {
    local file="$1"
    local pid
    pid="$(read_pid "${file}")"
    if [ -n "${pid}" ] && ! is_pid_running "${pid}"; then
        rm -f "${file}"
    fi
}

wait_for_http() {
    local url="$1"
    local retries="${2:-30}"
    local sleep_seconds="${3:-1}"
    local i

    for ((i = 1; i <= retries; i++)); do
        if curl -fsS "${url}" >/dev/null 2>&1; then
            return 0
        fi
        sleep "${sleep_seconds}"
    done
    return 1
}

port_pid() {
    local port="$1"
    lsof -ti :"${port}" 2>/dev/null | head -n 1 || true
}
