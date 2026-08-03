#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
export PROJECT_ROOT

SUPERVISOR_BIN="${PROJECT_ROOT}/index-tts/.venv/bin"
SUPERVISORD="${SUPERVISOR_BIN}/supervisord"
SUPERVISORCTL="${SUPERVISOR_BIN}/supervisorctl"
CONF="${PROJECT_ROOT}/supervisor/supervisord.conf"
PID_FILE="${PROJECT_ROOT}/data/run/supervisord.pid"

mkdir -p "${PROJECT_ROOT}/data/run" "${PROJECT_ROOT}/data/logs"

is_running() {
    if [ -f "${PID_FILE}" ]; then
        local pid
        pid="$(tr -d '[:space:]' < "${PID_FILE}")"
        [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null
    else
        return 1
    fi
}

ensure_supervisor_installed() {
    if [ ! -x "${SUPERVISORD}" ] || [ ! -x "${SUPERVISORCTL}" ]; then
        "${PROJECT_ROOT}/index-tts/.venv/bin/pip" install -q supervisor
    fi
}

cmd="${1:-up}"

case "${cmd}" in
    up)
        ensure_supervisor_installed
        if ! is_running; then
            "${SUPERVISORD}" -c "${CONF}"
        fi
        "${SUPERVISORCTL}" -c "${CONF}" status
        ;;
    down)
        if is_running; then
            "${SUPERVISORCTL}" -c "${CONF}" shutdown
        fi
        ;;
    restart)
        ensure_supervisor_installed
        if ! is_running; then
            "${SUPERVISORD}" -c "${CONF}"
        else
            "${SUPERVISORCTL}" -c "${CONF}" restart all
        fi
        "${SUPERVISORCTL}" -c "${CONF}" status
        ;;
    status)
        if is_running; then
            "${SUPERVISORCTL}" -c "${CONF}" status
        else
            echo "supervisord not running"
            exit 1
        fi
        ;;
    logs)
        tail -n 80 -f "${PROJECT_ROOT}/data/logs/backend.log" "${PROJECT_ROOT}/data/logs/frontend.log"
        ;;
    *)
        echo "usage: ./supervisor.sh {up|down|restart|status|logs}"
        exit 1
        ;;
esac
