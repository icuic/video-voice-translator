#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/scripts/common_env.sh"

BACKEND_PID_FILE="$(pid_file_for backend)"
FRONTEND_PID_FILE="$(pid_file_for frontend)"
BACKEND_LOG="$(log_file_for backend)"
FRONTEND_LOG="$(log_file_for frontend)"

usage() {
    cat <<'EOF'
用法:
  ./service.sh up         启动前后端
  ./service.sh down       停止前后端
  ./service.sh restart    重启前后端
  ./service.sh status     查看运行状态
  ./service.sh logs       查看日志
  ./service.sh urls       显示访问地址
  ./service.sh backend    仅启动后端
  ./service.sh frontend   仅启动前端
  ./service.sh stop-backend
  ./service.sh stop-frontend
EOF
}

start_backend() {
    remove_pid_file_if_stale "${BACKEND_PID_FILE}"
    local pid
    pid="$(read_pid "${BACKEND_PID_FILE}")"
    local port_owner
    port_owner="$(port_pid "${BACKEND_PORT}")"
    if [ -n "${pid}" ] && is_pid_running "${pid}"; then
        info "后端已在运行，PID=${pid}"
        return 0
    fi
    if [ -n "${port_owner}" ]; then
        error "端口 ${BACKEND_PORT} 已被进程 ${port_owner} 占用，请先释放后再启动。"
        exit 1
    fi

    ensure_backend_env
    info "启动后端服务..."
    nohup "${INDEX_TTS_DIR}/.venv/bin/python" -m uvicorn backend.app.main:app \
        --host "${BACKEND_HOST}" \
        --port "${BACKEND_PORT}" \
        --log-level info \
        > "${BACKEND_LOG}" 2>&1 &
    echo $! > "${BACKEND_PID_FILE}"

    if wait_for_http "http://127.0.0.1:${BACKEND_PORT}/health" 30 1; then
        info "后端已就绪: http://127.0.0.1:${BACKEND_PORT}/health"
    else
        error "后端启动失败，请查看日志: ${BACKEND_LOG}"
        tail -n 50 "${BACKEND_LOG}" || true
        exit 1
    fi
}

start_frontend() {
    remove_pid_file_if_stale "${FRONTEND_PID_FILE}"
    local pid
    pid="$(read_pid "${FRONTEND_PID_FILE}")"
    local port_owner
    port_owner="$(port_pid "${FRONTEND_PORT}")"
    if [ -n "${pid}" ] && is_pid_running "${pid}"; then
        info "前端已在运行，PID=${pid}"
        return 0
    fi
    if [ -n "${port_owner}" ]; then
        error "端口 ${FRONTEND_PORT} 已被进程 ${port_owner} 占用，请先释放后再启动。"
        exit 1
    fi

    ensure_frontend_env
    info "启动前端服务..."
    nohup bash -lc "cd '${PROJECT_ROOT}/frontend' && exec node ./node_modules/vite/bin/vite.js --host '${FRONTEND_HOST}' --port '${FRONTEND_PORT}'" \
        > "${FRONTEND_LOG}" 2>&1 &
    echo $! > "${FRONTEND_PID_FILE}"

    if wait_for_http "http://127.0.0.1:${FRONTEND_PORT}" 30 1; then
        info "前端已就绪: http://127.0.0.1:${FRONTEND_PORT}"
    else
        error "前端启动失败，请查看日志: ${FRONTEND_LOG}"
        tail -n 50 "${FRONTEND_LOG}" || true
        exit 1
    fi
}

stop_service() {
    local name="$1"
    local file="$2"
    remove_pid_file_if_stale "${file}"
    local pid
    pid="$(read_pid "${file}")"
    if [ -z "${pid}" ]; then
        info "${name}未运行"
        return 0
    fi

    if is_pid_running "${pid}"; then
        info "停止${name}，PID=${pid}"
        pkill -TERM -P "${pid}" 2>/dev/null || true
        kill "${pid}" 2>/dev/null || true
        sleep 1
        if is_pid_running "${pid}"; then
            warn "${name}仍在运行，发送 SIGKILL"
            pkill -KILL -P "${pid}" 2>/dev/null || true
            kill -9 "${pid}" 2>/dev/null || true
        fi
    fi
    rm -f "${file}"
}

show_status() {
    local backend_pid frontend_pid
    backend_pid="$(read_pid "${BACKEND_PID_FILE}")"
    frontend_pid="$(read_pid "${FRONTEND_PID_FILE}")"

    if [ -n "${backend_pid}" ] && is_pid_running "${backend_pid}"; then
        info "后端运行中: PID=${backend_pid}, URL=http://127.0.0.1:${BACKEND_PORT}"
    else
        info "后端未运行"
    fi

    if [ -n "${frontend_pid}" ] && is_pid_running "${frontend_pid}"; then
        info "前端运行中: PID=${frontend_pid}, URL=http://127.0.0.1:${FRONTEND_PORT}"
    else
        info "前端未运行"
    fi

    info "后端日志: ${BACKEND_LOG}"
    info "前端日志: ${FRONTEND_LOG}"
}

show_urls() {
    cat <<EOF
本机访问:
  前端: http://127.0.0.1:${FRONTEND_PORT}
  后端: http://127.0.0.1:${BACKEND_PORT}
  API 文档: http://127.0.0.1:${BACKEND_PORT}/docs

如使用 SSH 端口转发:
  ssh -i <私钥> -p <端口> <用户>@<服务器IP> -L 5173:127.0.0.1:${FRONTEND_PORT} -L 8000:127.0.0.1:${BACKEND_PORT} -N
  然后在本地浏览器访问:
    http://127.0.0.1:5173
    http://127.0.0.1:8000/docs
EOF
}

show_logs() {
    touch "${BACKEND_LOG}" "${FRONTEND_LOG}"
    tail -n 60 -f "${BACKEND_LOG}" "${FRONTEND_LOG}"
}

cmd="${1:-up}"

case "${cmd}" in
    up)
        start_backend
        start_frontend
        show_urls
        ;;
    down)
        stop_service "前端" "${FRONTEND_PID_FILE}"
        stop_service "后端" "${BACKEND_PID_FILE}"
        ;;
    restart)
        stop_service "前端" "${FRONTEND_PID_FILE}"
        stop_service "后端" "${BACKEND_PID_FILE}"
        start_backend
        start_frontend
        show_urls
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    urls)
        show_urls
        ;;
    backend)
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    stop-backend)
        stop_service "后端" "${BACKEND_PID_FILE}"
        ;;
    stop-frontend)
        stop_service "前端" "${FRONTEND_PID_FILE}"
        ;;
    *)
        usage
        exit 1
        ;;
esac
