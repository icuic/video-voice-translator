#!/bin/bash
# AI 音视频翻译系统 - LLM 配置向导
# 交互式配置 OpenAI 兼容 LLM 参数，并写入项目根目录 .env 文件
#
# 用法：
#   ./configure.sh
#
# 注意：
#   - 配置完成后会自动重启 supervisord 管理的服务
#   - .env 中与镜像/网络相关的变量（MIRROR_MODE / HF_ENDPOINT 等）会被保留

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE="${PROJECT_ROOT}/.env.example"
MANAGE_SUPERVISOR="${PROJECT_ROOT}/manage-supervisor.sh"

MIRROR_VARS=(MIRROR_MODE HF_ENDPOINT USE_MODELSCOPE UV_DEFAULT_INDEX NPM_REGISTRY NODE_SETUP_URL HF_HUB_OFFLINE TRANSFORMERS_OFFLINE UV_HTTP_TIMEOUT)

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

if [ ! -f "${ENV_FILE}" ]; then
    if [ -f "${ENV_EXAMPLE}" ]; then
        cp "${ENV_EXAMPLE}" "${ENV_FILE}"
        log_warn ".env 不存在，已从 .env.example 复制模板"
    else
        touch "${ENV_FILE}"
        log_warn ".env 和 .env.example 均不存在，已创建空 .env"
    fi
fi

read_preserved_vars() {
    local key value line
    declare -Ag PRESERVED=()
    while IFS= read -r line || [ -n "${line}" ]; do
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "${line}" || "${line}" == \#* || "${line}" != *"="* ]] && continue
        key="${line%%=*}"
        value="${line#*=}"
        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        if [[ "${value}" == \"*\" ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "${value}" == \'*\' ]]; then
            value="${value:1:${#value}-2}"
        fi
        PRESERVED["${key}"]="${value}"
    done < "${ENV_FILE}"
}

prompt_value() {
    local prompt="$1"
    local default="${2:-}"
    local var_name="$3"
    local input
    local existing=""
    if [ -n "${var_name}" ] && [ -n "${PRESERVED[${var_name}]+x}" ]; then
        existing="${PRESERVED[${var_name}]}"
    fi
    if [ -n "${default}" ]; then
        if [ -n "${existing}" ]; then
            read -r -p "$(echo -e "${COLOR_BOLD}  ${prompt}${COLOR_RESET} ${COLOR_YELLOW}[当前: ${existing:0:10}$([ ${#existing} -gt 10 ] && echo -n "…")${COLOR_RESET}]  > ")" input
        else
            read -r -p "$(echo -e "${COLOR_BOLD}  ${prompt}${COLOR_RESET} ${COLOR_CYAN}[默认: ${default}]${COLOR_RESET}  > ")" input
        fi
        input="${input:-${default}}"
    else
        if [ -n "${existing}" ]; then
            read -r -p "$(echo -e "${COLOR_BOLD}  ${prompt}${COLOR_RESET} ${COLOR_YELLOW}[当前: ${existing:0:10}$([ ${#existing} -gt 10 ] && echo -n "…")${COLOR_RESET}]  > ")" input
        else
            read -r -p "$(echo -e "${COLOR_BOLD}  ${prompt}${COLOR_RESET}  > ")" input
        fi
    fi
    while [ -z "${input}" ] && [ -z "${default}" ]; do
        log_error "此项为必填，请重新输入"
        if [ -n "${existing}" ]; then
            read -r -p "$(echo -e "${COLOR_BOLD}  ${prompt}${COLOR_RESET} ${COLOR_YELLOW}[当前: ${existing:0:10}$([ ${#existing} -gt 10 ] && echo -n "…")${COLOR_RESET}]  > ")" input
        else
            read -r -p "$(echo -e "${COLOR_BOLD}  ${prompt}${COLOR_RESET}  > ")" input
        fi
    done
    if [ -n "${existing}" ] && [ -z "${input}" ]; then
        input="${existing}"
    fi
    echo -n "${input}"
}

validate_url() {
    case "$1" in
        http://*|https://*) return 0 ;;
        *) return 1 ;;
    esac
}

validate_temperature() {
    local val="$1"
    if [[ "${val}" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        awk -v v="${val}" 'BEGIN { exit !(v>=0.0 && v<=2.0) }' && return 0 || return 1
    fi
    return 1
}

validate_timeout() {
    [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

confirm() {
    local prompt="$1"
    local default_yes="${2:-true}"
    local hint input
    if ${default_yes}; then
        hint="[Y/n]"
    else
        hint="[y/N]"
    fi
    read -r -p "$(echo -e "${COLOR_BOLD}${prompt}${COLOR_RESET} ${hint} ")" input
    input="$(echo "${input:-}" | tr '[:upper:]' '[:lower:]')"
    if ${default_yes}; then
        [[ "${input}" != "n" && "${input}" != "no" ]]
    else
        [[ "${input}" == "y" || "${input}" == "yes" ]]
    fi
}

echo ""
echo -e "${COLOR_BOLD}╔════════════════════════════════════════════════════════════╗${COLOR_RESET}"
echo -e "${COLOR_BOLD}║   AI 音视频翻译系统 - 配置向导 v1.0.0                      ║${COLOR_RESET}"
echo -e "${COLOR_BOLD}║   LLM 配置采用 OpenAI 兼容协议，请完整填写以下信息         ║${COLOR_RESET}"
echo -e "${COLOR_BOLD}╚════════════════════════════════════════════════════════════╝${COLOR_RESET}"
echo ""

read_preserved_vars

log_info "读取现有配置完成（镜像/网络类变量将被自动保留）"
echo ""

echo -e "${COLOR_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${COLOR_RESET}"
echo -e "${COLOR_BOLD} 第 1 步 / 共 2 步：填写必填配置（OpenAI 兼容三件套）${COLOR_RESET}"
echo -e "${COLOR_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${COLOR_RESET}"
echo ""

LLM_BASE_URL="$(prompt_value "API Base URL（http 或 https 开头）" "" "LLM_BASE_URL")"
while ! validate_url "${LLM_BASE_URL}"; do
    log_error "Base URL 必须以 http:// 或 https:// 开头，请重新输入"
    LLM_BASE_URL="$(prompt_value "API Base URL（http 或 https 开头）" "" "LLM_BASE_URL")"
done
log_success "Base URL 格式正确"
echo ""

LLM_API_KEY="$(prompt_value "API Key（本地无鉴权部署填 EMPTY）" "" "LLM_API_KEY")"
log_success "API Key 已录入"
echo ""

LLM_MODEL="$(prompt_value "模型名（按供应商文档填写）" "" "LLM_MODEL")"
log_success "模型名 已录入"
echo ""

echo -e "${COLOR_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${COLOR_RESET}"
echo -e "${COLOR_BOLD} 第 2 步 / 共 2 步：可选高级参数（直接回车使用默认值）${COLOR_RESET}"
echo -e "${COLOR_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${COLOR_RESET}"
echo ""

LLM_TEMPERATURE=""
if confirm "是否配置 LLM 采样温度？" false; then
    LLM_TEMPERATURE="$(prompt_value "采样温度（0.0~2.0，翻译推荐 0.05~0.2）" "0.1" "LLM_TEMPERATURE")"
    while ! validate_temperature "${LLM_TEMPERATURE}"; do
        log_error "温度必须是 0.0~2.0 之间的数字，请重新输入"
        LLM_TEMPERATURE="$(prompt_value "采样温度（0.0~2.0，翻译推荐 0.05~0.2）" "0.1" "LLM_TEMPERATURE")"
    done
    log_success "温度 = ${LLM_TEMPERATURE}"
    echo ""
fi

LLM_TIMEOUT=""
if confirm "是否配置请求超时时间？" false; then
    LLM_TIMEOUT="$(prompt_value "单次请求超时秒数（建议 300~600）" "300" "LLM_TIMEOUT")"
    while ! validate_timeout "${LLM_TIMEOUT}"; do
        log_error "超时必须是正整数，请重新输入"
        LLM_TIMEOUT="$(prompt_value "单次请求超时秒数（建议 300~600）" "300" "LLM_TIMEOUT")"
    done
    log_success "超时 = ${LLM_TIMEOUT}s"
    echo ""
fi

echo ""
echo -e "${COLOR_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${COLOR_RESET}"
echo -e "${COLOR_BOLD} 即将写入以下配置到 .env：${COLOR_RESET}"
echo -e "${COLOR_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${COLOR_RESET}"
echo ""
echo -e "  LLM_BASE_URL     = ${COLOR_CYAN}${LLM_BASE_URL}${COLOR_RESET}"
MASKED_KEY="${LLM_API_KEY}"
if [ "${#MASKED_KEY}" -gt 8 ]; then
    MASKED_KEY="${MASKED_KEY:0:4}…${MASKED_KEY: -4}"
fi
echo -e "  LLM_API_KEY      = ${COLOR_CYAN}${MASKED_KEY}${COLOR_RESET}（已脱敏显示）"
echo -e "  LLM_MODEL        = ${COLOR_CYAN}${LLM_MODEL}${COLOR_RESET}"
if [ -n "${LLM_TEMPERATURE}" ]; then
    echo -e "  LLM_TEMPERATURE  = ${COLOR_CYAN}${LLM_TEMPERATURE}${COLOR_RESET}"
else
    echo -e "  LLM_TEMPERATURE  = ${COLOR_YELLOW}（未设置，走代码默认）${COLOR_RESET}"
fi
if [ -n "${LLM_TIMEOUT}" ]; then
    echo -e "  LLM_TIMEOUT      = ${COLOR_CYAN}${LLM_TIMEOUT}s${COLOR_RESET}"
else
    echo -e "  LLM_TIMEOUT      = ${COLOR_YELLOW}（未设置，走代码默认）${COLOR_RESET}"
fi
echo -e "  DASHSCOPE_API_KEY= ${COLOR_YELLOW}（已置空，防止优先级冲突）${COLOR_RESET}"
echo ""
for k in "${MIRROR_VARS[@]}"; do
    if [ -n "${PRESERVED[${k}]+x}" ] && [ -n "${PRESERVED[${k}]}" ]; then
        echo -e "  ${k}${COLOR_GREEN} ← 保留原值${COLOR_RESET}"
    fi
done
echo ""

if ! confirm "确认写入以上配置？" true; then
    log_warn "用户取消，未写入任何改动"
    exit 0
fi

TMP_ENV="$(mktemp)"
{
    echo "# 复制本文件为 .env（HAI 镜像用户已自动备好）"
    echo "# 详细配置说明：docs/ENV_ADVANCED.md"
    echo ""
    echo "# 必填：OpenAI 兼容 LLM 配置（/v1/chat/completions）"
    echo "LLM_BASE_URL=${LLM_BASE_URL}"
    echo "LLM_API_KEY=${LLM_API_KEY}"
    echo "LLM_MODEL=${LLM_MODEL}"
    echo ""
    echo "# 可选：LLM 调优参数（留空走代码默认值）"
    if [ -n "${LLM_TEMPERATURE}" ]; then
        echo "LLM_TEMPERATURE=${LLM_TEMPERATURE}"
    else
        echo "# LLM_TEMPERATURE=0.1"
    fi
    if [ -n "${LLM_TIMEOUT}" ]; then
        echo "LLM_TIMEOUT=${LLM_TIMEOUT}"
    else
        echo "# LLM_TIMEOUT=300"
    fi
    echo ""
    echo "# HAI 镜像专用（无需修改）"
    for k in MIRROR_MODE HF_ENDPOINT USE_MODELSCOPE UV_DEFAULT_INDEX NPM_REGISTRY NODE_SETUP_URL UV_HTTP_TIMEOUT; do
        if [ -n "${PRESERVED[${k}]+x}" ] && [ -n "${PRESERVED[${k}]}" ]; then
            echo "${k}=${PRESERVED[${k}]}"
        fi
    done
    if [ -n "${PRESERVED[HF_HUB_OFFLINE]+x}" ] && [ -n "${PRESERVED[HF_HUB_OFFLINE]}" ]; then
        echo "# HF_HUB_OFFLINE=${PRESERVED[HF_HUB_OFFLINE]}"
    fi
    if [ -n "${PRESERVED[TRANSFORMERS_OFFLINE]+x}" ] && [ -n "${PRESERVED[TRANSFORMERS_OFFLINE]}" ]; then
        echo "# TRANSFORMERS_OFFLINE=${PRESERVED[TRANSFORMERS_OFFLINE]}"
    fi
    if [ -z "${PRESERVED[MIRROR_MODE]+x}" ]; then
        echo "MIRROR_MODE=tencent-intranet"
    fi
    if [ -z "${PRESERVED[HF_ENDPOINT]+x}" ]; then
        echo "HF_ENDPOINT=https://hf-mirror.com"
    fi
    if [ -z "${PRESERVED[USE_MODELSCOPE]+x}" ]; then
        echo "USE_MODELSCOPE=true"
    fi
} > "${TMP_ENV}"

mv "${TMP_ENV}" "${ENV_FILE}"
log_success ".env 已写入（${ENV_FILE}）"
echo ""

if [ -x "${MANAGE_SUPERVISOR}" ]; then
    if confirm "配置已写入，是否立即重启服务让配置生效？" true; then
        log_info "正在重启服务（./manage-supervisor.sh restart）..."
        if "${MANAGE_SUPERVISOR}" restart 2>&1 | tail -n 5; then
            log_success "服务已重启，请访问 Web UI 使用：http://<公网IP>:5173"
        else
            log_warn "服务重启过程中有告警，请执行 './manage-supervisor.sh status' 确认状态"
        fi
    else
        echo ""
        log_warn "已跳过重启。稍后手动执行 './manage-supervisor.sh restart' 即可生效"
    fi
else
    log_warn "未找到 manage-supervisor.sh，请手动重启服务以加载新配置"
fi

echo ""
log_success "配置向导完成。"
echo ""
