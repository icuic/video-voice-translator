#!/bin/bash
# AI 音视频翻译系统 - 一键更新脚本
# 拉取最新代码 + 增量更新依赖 + 重启服务
# 注意：此脚本绝不修改用户的 .env 配置

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
MANAGE_SUPERVISOR="${PROJECT_ROOT}/manage-supervisor.sh"
ENV_FILE="${PROJECT_ROOT}/.env"

COLOR_BOLD=$'\033[1m'
COLOR_GREEN=$'\033[32m'
COLOR_YELLOW=$'\033[33m'
COLOR_CYAN=$'\033[36m'
COLOR_RED=$'\033[31m'
COLOR_RESET=$'\033[0m'

log_info()    { echo -e "${COLOR_CYAN}[INFO]${COLOR_RESET}  $*"; }
log_success() { echo -e "${COLOR_GREEN}[OK]${COLOR_RESET}    $*"; }
log_warn()    { echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET}  $*"; }
log_error()   { echo -e "${COLOR_RED}[ERR]${COLOR_RESET}   $*" >&2; }

cd "${PROJECT_ROOT}"

echo ""
echo -e "${COLOR_BOLD}╔════════════════════════════════════════════════════════════╗${COLOR_RESET}"
echo -e "${COLOR_BOLD}║   AI 音视频翻译系统 - 项目更新脚本 v1.0.0                  ║${COLOR_RESET}"
echo -e "${COLOR_BOLD}╚════════════════════════════════════════════════════════════╝${COLOR_RESET}"
echo ""

if [ ! -d "${PROJECT_ROOT}/.git" ]; then
    log_error "项目目录不是 Git 仓库，无法通过 git pull 更新。"
    log_error "请手动拉取最新代码后重跑本脚本，或重新下载项目。"
    exit 1
fi

log_info "第 1/4 步：拉取最新代码..."
if git pull --ff-only; then
    NEW_VERSION="$(git -C "${PROJECT_ROOT}" describe --tags --always 2>/dev/null || git -C "${PROJECT_ROOT}" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
    log_success "代码已更新到最新版本：${NEW_VERSION}"
else
    log_warn "git pull --ff-only 失败，尝试 rebase 拉取..."
    if git pull --rebase; then
        log_success "代码已通过 rebase 更新到最新"
    else
        log_error "代码拉取失败，存在本地改动与远程冲突。"
        log_error "请先手动处理冲突，或执行以下命令强制覆盖本地改动（会丢失本地修改）："
        echo ""
        echo "    git stash && git pull --ff-only"
        echo ""
        exit 1
    fi
fi
echo ""

if [ -f "${ENV_FILE}" ]; then
    log_info "检测到 .env，已跳过（用户配置绝不修改）"
fi
echo ""

log_info "第 2/4 步：更新 Python 依赖（如需）..."
if [ -f "${PROJECT_ROOT}/requirements_project.txt" ]; then
    if [ -d "${PROJECT_ROOT}/.venv" ] && [ -x "${PROJECT_ROOT}/.venv/bin/uv" ]; then
        if "${PROJECT_ROOT}/.venv/bin/uv" pip sync "${PROJECT_ROOT}/requirements_project.txt" --quiet 2>/dev/null; then
            log_success "Python 依赖已同步（通过 .venv/uv）"
        else
            log_warn ".venv/uv 同步失败，尝试 pip install -r..."
            "${PROJECT_ROOT}/.venv/bin/python" -m pip install -r "${PROJECT_ROOT}/requirements_project.txt" -q
            log_success "Python 依赖已同步（通过 .venv/pip）"
        fi
    elif command -v uv >/dev/null 2>&1; then
        if uv pip sync "${PROJECT_ROOT}/requirements_project.txt" --quiet 2>/dev/null; then
            log_success "Python 依赖已同步（通过 uv）"
        else
            log_warn "uv 同步失败，尝试 pip install -r..."
            python -m pip install -r "${PROJECT_ROOT}/requirements_project.txt" -q
            log_success "Python 依赖已同步（通过 pip）"
        fi
    else
        log_warn "未找到 uv 或 .venv，尝试系统 python pip 安装..."
        python -m pip install -r "${PROJECT_ROOT}/requirements_project.txt" -q 2>/dev/null || \
            log_warn "系统 pip 同步失败，请手动执行：pip install -r requirements_project.txt"
    fi
else
    log_warn "未找到 requirements_project.txt，跳过 Python 依赖更新"
fi
echo ""

log_info "第 3/4 步：更新前端依赖并重新构建（如需）..."
if [ -d "${PROJECT_ROOT}/frontend/node_modules" ] && [ -f "${PROJECT_ROOT}/frontend/package.json" ]; then
    if command -v npm >/dev/null 2>&1; then
        (
            cd "${PROJECT_ROOT}/frontend"
            if npm install --no-audit --no-fund --silent 2>/dev/null; then
                log_success "前端依赖已同步"
            else
                log_warn "npm install 执行时有告警，但可能不影响使用"
            fi
        )
    else
        log_warn "未找到 npm，跳过前端依赖同步"
    fi
else
    log_warn "未检测到前端环境（可能是首次安装），跳过前端依赖更新"
fi
echo ""

if [ -x "${MANAGE_SUPERVISOR}" ]; then
    log_info "第 4/4 步：重启服务..."
    if "${MANAGE_SUPERVISOR}" restart 2>&1 | tail -n 8; then
        log_success "服务已重启"
        echo ""
        log_success "═══════════════════════════════════════════════"
        log_success " 更新完成！"
        [ -n "${NEW_VERSION:-}" ] && log_success " 当前版本：${NEW_VERSION}"
        log_success " 前端 Web UI：http://<公网IP>:5173"
        log_success " API 文档：  http://<公网IP>:8000/docs"
        log_success "═══════════════════════════════════════════════"
        echo ""
    else
        log_warn "服务重启时有告警，请手动确认："
        echo "    ./manage-supervisor.sh status"
    fi
else
    log_warn "未找到 manage-supervisor.sh，请手动重启服务。"
fi
