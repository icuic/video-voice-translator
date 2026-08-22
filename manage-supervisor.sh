#!/bin/bash
# Video Voice Translator - Supervisor 管理脚本
# 用法：
#   ./manage-supervisor.sh start        # 启动 supervisord + 所有服务
#   ./manage-supervisor.sh stop     # 停止所有服务 + 退出 supervisord
#   ./manage-supervisor.sh restart  # 重启所有服务
#   ./manage-supervisor.sh status   # 查看所有服务状态
#   ./manage-supervisor.sh reload   # 重新加载配置（不中断服务）
#   ./manage-supervisor.sh restart-backend / restart-frontend / stop-backend / ...
#   ./manage-supervisor.sh logs     # 滚动查看所有服务日志
#   ./manage-supervisor.sh logs-backend   # 只看后端日志
#   ./manage-supervisor.sh logs-frontend # 只看前端日志

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
CONF_FILE="${PROJECT_ROOT}/supervisor/supervisord.conf"
SOCK_FILE="${PROJECT_ROOT}/data/run/supervisor.sock"
PID_FILE="${PROJECT_ROOT}/data/run/supervisord.pid"
LOG_DIR="${PROJECT_ROOT}/data/logs/supervisor"

# 环境变量注入给 supervisord 配置（供 %(ENV_XXX)s 语法对应 shell 中 XXX）
# 说明：ini 文件中用的是 %(ENV_PROJECT_ROOT)s / %(ENV_USER)s，
# 因此我们既要 export PROJECT_ROOT / USER，也要 export 前缀版 ENV_PROJECT_ROOT / ENV_USER，
# 防止 restart 时 supervisord 重新读取配置导致 ENV_PROJECT_ROOT 为空，command 变成空路径崩溃
export PROJECT_ROOT="${PROJECT_ROOT}"
export USER="$(id -un)"
export ENV_PROJECT_ROOT="${PROJECT_ROOT}"
export ENV_USER="${USER}"


# 将 PROJECT_ROOT/.env 中的全部 LLM/MIRROR/HF 相关键 export 到当前 shell，
# 同时生成前缀 ENV_* 版本（供 backend.ini 中的 %(ENV_LLM_BASE_URL)s 等语法读取）。
#
# 重要：此函数必须在所有子命令（start/restart/restart-backend/stop/status）入口处
# 无条件调用一次，即便 start_supervisor() 里的 pgrep guard 命中直接 return，也要执行。
# 因为如果 supervisord 已经在运行，那么 "restart-backend" / "restart" 会走
# supervisorctl restart 路径，supervisord daemon 会重新展开 environment 字段的
# %(ENV_XXX)s % 语法——而 % 展开时 supervisord daemon 会从"调用方 supervisorctl
# 进程"身上继承的环境变量里取（或者说从它自己 fork supervisorctl 时的 env 里取，
# 但无论哪种模型，只要当前 shell export 了 XXX/ENV_XXX，后续子进程就能看到，
# supervisor 内部的 %(ENV_XXX)s 也能读到）。
_export_dotenv_keys_to_shell() {
    if [ -f "${PROJECT_ROOT}/.env" ]; then
        _SAFE_DOTENV="$(mktemp /tmp/vvt-manage-supervisor-dotenv.XXXXXX)"
        awk '
            BEGIN { FS="=" }
            {
                line=$0
                sub(/^[ \t]+/, "", line)
                sub(/[ \t\r]+$/, "", line)
                if (length(line)==0) next
                if (substr(line,1,1)=="#") next
                if (index(line,"=")==0) next
                key=substr(line,1,index(line,"=")-1)
                if (key !~ /^[A-Za-z_][A-Za-z0-9_]*$/) next
                print line
            }
        ' < "${PROJECT_ROOT}/.env" > "${_SAFE_DOTENV}"
        set -a
        # shellcheck disable=SC1090
        . "${_SAFE_DOTENV}"
        set +a
        rm -f "${_SAFE_DOTENV}"
    fi

    _NORMALIZE_KEYS=(LLM_BASE_URL LLM_API_KEY LLM_MODEL LLM_TEMPERATURE LLM_TIMEOUT DASHSCOPE_API_KEY MIRROR_MODE HF_ENDPOINT USE_MODELSCOPE HF_HOME HF_HUB_DISABLE_TELEMETRY)
    for _k in "${_NORMALIZE_KEYS[@]}"; do
        _v="${!_k:-}"
        if [ "${#_v}" -ge 2 ]; then
            case "${_v}" in
                \"*\"|\'*\'|\`*\`)
                    _v="${_v:1:${#_v}-2}"
                    ;;
            esac
        fi
        export "${_k}=${_v}"
        export "ENV_${_k}=${_v}"
    done
    unset _NORMALIZE_KEYS _k _v _SAFE_DOTENV
}
# 脚本第一次加载时就跑一次，确保后面所有函数/子命令分支都能读到。
_export_dotenv_keys_to_shell

# 创建必要目录
mkdir -p "${PROJECT_ROOT}/data/run" "${LOG_DIR}"

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 检查 supervisord 是否安装
if ! command -v supervisord >/dev/null 2>&1; then
    echo -e "${RED}❌ 错误: 系统未安装 supervisord${NC}"
    echo "   Ubuntu/Debian: sudo apt-get install -y supervisor"
    echo "   或通过 pip:  pip install supervisor"
    exit 1
fi

_is_supervisord_running() {
    if [ -S "$SOCK_FILE" ] && supervisorctl -s "unix://${SOCK_FILE}" status >/dev/null 2>&1; then
        return 0
    fi
    # 如果 socket 没了但 pid 在，说明进程仍存活
    if [ -f "$PID_FILE" ]; then
        local _pid
        _pid=$(cat "$PID_FILE" 2>/dev/null || echo "")
        if [ -n "$_pid" ] && ps -p "$_pid" >/dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

_ctl() {
    if ! _is_supervisord_running; then
        echo -e "${RED}❌ supervisord 未运行${NC}"
        echo "   请先运行: $0 start"
        exit 1
    fi
    supervisorctl -c "${CONF_FILE}" -s "unix://${SOCK_FILE}" "$@"
}

start_supervisord() {
    if _is_supervisord_running; then
        echo -e "${YELLOW}⚠️  supervisord 已经在运行中${NC}"
        echo "   查看状态: $0 status"
        return 0
    fi
    echo -e "${BLUE}🚀 启动 supervisord...${NC}"
    supervisord -c "$CONF_FILE"
    sleep 2
    if _is_supervisord_running; then
        echo -e "${GREEN}✅ supervisord 启动成功${NC}"
        echo "   配置文件: ${CONF_FILE}"
        echo "   Socket    : ${SOCK_FILE}"
        echo ""
        show_status
    else
        echo -e "${RED}❌ supervisord 启动失败，请查看日志: ${LOG_DIR}/supervisord.log${NC}"
        exit 1
    fi
}

stop_supervisord() {
    if ! _is_supervisord_running; then
        echo -e "${YELLOW}⚠️  supervisord 未运行${NC}"
        return 0
    fi
    echo -e "${BLUE}🛑 停止所有服务并退出 supervisord...${NC}"
    supervisorctl -c "${CONF_FILE}" -s "unix://${SOCK_FILE}" shutdown || true
    # 等待退出
    for i in $(seq 1 20); do
        if ! _is_supervisord_running; then
            break
        fi
        sleep 1
    done
    rm -f "$SOCK_FILE" "$PID_FILE"
    echo -e "${GREEN}✅ supervisord 已停止${NC}"
}

show_status() {
    if ! _is_supervisord_running; then
        echo -e "${YELLOW}⚠️  supervisord 未运行${NC}"
        echo "   启动: $0 start"
        return 0
    fi
    echo ""
    echo -e "${BLUE}======================== 服务状态 ========================${NC}"
    _ctl status all || true
    echo -e "${BLUE}=========================================================${NC}"
    echo ""
    echo -e "访问地址："
    echo -e "  前端界面 : ${GREEN}http://localhost:5173${NC}"
    echo -e "  后端API : ${GREEN}http://localhost:8000${NC}"
    echo -e "  API文档: ${GREEN}http://localhost:8000/docs${NC}"
    echo -e "  日志目录: ${LOG_DIR}"
}

show_logs() {
    local target="$1"
    if ! _is_supervisord_running; then
        echo -e "${RED}❌ supervisord 未运行${NC}"
        exit 1
    fi
    case "$target" in
        backend)
            echo -e "${BLUE}📋 实时查看后端日志（Ctrl+C 退出）${NC}"
            tail -n 100 -f "${LOG_DIR}/backend.log" "${LOG_DIR}/backend.err.log"
            ;;
        frontend)
            echo -e "${BLUE}📋 实时查看前端日志（Ctrl+C 退出）${NC}"
            tail -n 100 -f "${LOG_DIR}/frontend.log" "${LOG_DIR}/frontend.err.log"
            ;;
        ""|all)
            echo -e "${BLUE}📋 实时查看所有日志（Ctrl+C 退出）${NC}"
            tail -n 100 -f "${LOG_DIR}/backend.log" "${LOG_DIR}/backend.err.log" "${LOG_DIR}/frontend.log" "${LOG_DIR}/frontend.err.log"
            ;;
        *)
            echo "未知目标: $target，可用: backend / frontend / all"
            exit 1
            ;;
    esac
}

reload_config() {
    if ! _is_supervisord_running; then
        echo -e "${RED}❌ supervisord 未运行${NC}"
        exit 1
    fi
    echo -e "${BLUE}🔄 重新加载配置...${NC}"
    _ctl reread
    _ctl update
    echo -e "${GREEN}✅ 配置已重新加载${NC}"
}

case "${1:-status}" in
    start|up)
        _export_dotenv_keys_to_shell
        start_supervisord
        ;;
    stop|down|shutdown)
        _export_dotenv_keys_to_shell
        stop_supervisord
        ;;
    restart)
        _export_dotenv_keys_to_shell
        if _is_supervisord_running; then
            echo -e "${BLUE}🔄 重启所有服务...${NC}"
            _ctl restart all
            sleep 2
            show_status
        else
            echo -e "${YELLOW}ℹ️  supervisord 未运行，改为直接启动${NC}"
            start_supervisord
        fi
        ;;
    status)
        _export_dotenv_keys_to_shell
        show_status
        ;;
    reload|reread|update)
        _export_dotenv_keys_to_shell
        reload_config
        ;;
    restart-backend)
        _export_dotenv_keys_to_shell
        echo -e "${BLUE}🔄 重启后端...${NC}"
        _ctl restart vvt-backend
        _ctl status vvt-backend
        ;;
    restart-frontend)
        _export_dotenv_keys_to_shell
        echo -e "${BLUE}🔄 重启前端...${NC}"
        _ctl restart vvt-frontend
        _ctl status vvt-frontend
        ;;
    stop-backend)
        _export_dotenv_keys_to_shell
        echo -e "${BLUE}🛑 停止后端...${NC}"
        _ctl stop vvt-backend
        _ctl status vvt-backend
        ;;
    stop-frontend)
        _export_dotenv_keys_to_shell
        echo -e "${BLUE}🛑 停止前端...${NC}"
        _ctl stop vvt-frontend
        _ctl status vvt-frontend
        ;;
    start-backend)
        _export_dotenv_keys_to_shell
        echo -e "${BLUE}🚀 启动后端...${NC}"
        _ctl start vvt-backend
        _ctl status vvt-backend
        ;;
    start-frontend)
        _export_dotenv_keys_to_shell
        echo -e "${BLUE}🚀 启动前端...${NC}"
        _ctl start vvt-frontend
        _ctl status vvt-frontend
        ;;
    logs)
        _export_dotenv_keys_to_shell
        show_logs all
        ;;
    logs-backend)
        _export_dotenv_keys_to_shell
        show_logs backend
        ;;
    logs-frontend)
        _export_dotenv_keys_to_shell
        show_logs frontend
        ;;
    ctl)
        _export_dotenv_keys_to_shell
        shift
        if [ $# -eq 0 ]; then
            echo "用法: $0 ctl <supervisorctl 命令...>"
            echo "示例: $0 ctl tail vvt-backend stdout"
            exit 1
        fi
        _ctl "$@"
        ;;
    help|--help|-h)
        echo "Video Voice Translator - Supervisor 管理脚本"
        echo ""
        echo "用法: $0 <命令>"
        echo ""
        echo "Supervisord 生命周期:"
        echo "  start          启动 supervisord + 所有服务"
        echo "  stop          停止所有服务 + 退出 supervisord"
        echo "  restart       重启所有服务（supervisord 未运行则直接启动）"
        echo "  status       查看所有服务状态"
        echo "  reload        重新加载配置文件"
        echo ""
        echo "单个服务操作:"
        echo "  start-backend / start-frontend"
        echo "  stop-backend  / stop-frontend"
        echo "  restart-backend / restart-frontend"
        echo ""
        echo "日志:"
        echo "  logs              实时查看全部日志"
        echo "  logs-backend     实时查看后端日志"
        echo "  logs-frontend   实时查看前端日志"
        echo ""
        echo "直接透传 supervisorctl 命令:"
        echo "  ctl <supervisorctl 选项>"
        echo ""
        exit 0
        ;;
    *)
        echo -e "${RED}❌ 未知命令: $1${NC}"
        echo "   查看帮助: $0 help"
        exit 1
        ;;
esac
