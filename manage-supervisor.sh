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
export PROJECT_ROOT="${PROJECT_ROOT}"
export USER="$(id -un)"

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
        start_supervisord
        ;;
    stop|down|shutdown)
        stop_supervisord
        ;;
    restart)
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
        show_status
        ;;
    reload|reread|update)
        reload_config
        ;;
    restart-backend)
        echo -e "${BLUE}🔄 重启后端...${NC}"
        _ctl restart vvt-backend
        _ctl status vvt-backend
        ;;
    restart-frontend)
        echo -e "${BLUE}🔄 重启前端...${NC}"
        _ctl restart vvt-frontend
        _ctl status vvt-frontend
        ;;
    stop-backend)
        echo -e "${BLUE}🛑 停止后端...${NC}"
        _ctl stop vvt-backend
        _ctl status vvt-backend
        ;;
    stop-frontend)
        echo -e "${BLUE}🛑 停止前端...${NC}"
        _ctl stop vvt-frontend
        _ctl status vvt-frontend
        ;;
    start-backend)
        echo -e "${BLUE}🚀 启动后端...${NC}"
        _ctl start vvt-backend
        _ctl status vvt-backend
        ;;
    start-frontend)
        echo -e "${BLUE}🚀 启动前端...${NC}"
        _ctl start vvt-frontend
        _ctl status vvt-frontend
        ;;
    logs)
        show_logs all
        ;;
    logs-backend)
        show_logs backend
        ;;
    logs-frontend)
        show_logs frontend
        ;;
    ctl)
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
