#!/bin/bash
# ============================================================
# AI 音视频翻译系统 - HAI 一键部署脚本
#
# 用途：用户从作者推广链接 https://curl.qcloud.com/9j4S4Hug
#       购买同款 V100 32GB HAI 实例后，SSH 登录执行本脚本即可
#       自动完成「拉代码 → 预置 .env 模板 → 安装依赖 →
#       写入 MOTD 欢迎横幅 → 启动后端/前端服务」。
#
# 用法（一行命令，推荐 bash 执行）：
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh)"
#
# 国内加速镜像（ghproxy 代理）：
#   bash -c "$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh)"
#
# 无 curl 用 wget：
#   wget -O - https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh | bash
#
# 本地调试（项目目录内）：
#   ./hai-deploy.sh --local
# ============================================================

set -euo pipefail

COLOR_BOLD='\033[1m'
COLOR_GREEN='\033[32m'
COLOR_YELLOW='\033[33m'
COLOR_RED='\033[31m'
COLOR_CYAN='\033[36m'
COLOR_RESET='\033[0m'

log_info()    { echo -e "${COLOR_CYAN}[INFO]${COLOR_RESET} $*"; }
log_success() { echo -e "${COLOR_GREEN}[OK]  ${COLOR_RESET} $*"; }
log_warn()    { echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $*"; }
log_error()   { echo -e "${COLOR_RED}[ERR] ${COLOR_RESET} $*" >&2; }
log_section() { echo ""; echo -e "${COLOR_BOLD}${COLOR_CYAN}▶ $*${COLOR_RESET}"; echo ""; }

REPO_DEFAULT="https://github.com/icuic/video-voice-translator.git"
BRANCH_DEFAULT="master"
INSTALL_DIR_DEFAULT="${HOME}/video-voice-translator"

LOCAL_MODE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --local) LOCAL_MODE=1; shift ;;
        --repo)  REPO_DEFAULT="$2"; shift 2 ;;
        --branch) BRANCH_DEFAULT="$2"; shift 2 ;;
        --dir)   INSTALL_DIR_DEFAULT="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,15p' "$0"
            exit 0
            ;;
        *) log_error "未知参数: $1"; exit 1 ;;
    esac
done

trap 'log_error "❌ 部署在第 $LINENO 行失败，请把完整报错截图发 Issue 或作者"; exit 1' ERR

banner() {
    cat <<'BANNER'
   ___   ______   ______   __    __  ________
  /   | /      | /      | /  |  /  |/        |
  $$/  |$$$$$$  |$$$$$$  |$$ |  $$ |$$$$$$$$/
  $$/     / $$/    / $$/ $$ |__$$ |$$ |__
  $$     / $$/    / $$/  $$    $$ |$$    |
  $$    / $$/    / $$/   $$$$$$$$ |$$$$$/
  $$   / $$/__  / $$/__       $$ |$$ |_____
  $$  /$$$$$$ |/$$$$$$  |      $$ |$$       |
  $$/ $$$$$$/ $$$$$$$$/       $$/ $$$$$$$$/

    AI 音视频翻译系统 · HAI 一键部署脚本
BANNER
}

detect_hai_env() {
    log_info "检测运行环境..."
    if command -v nvidia-smi >/dev/null 2>&1; then
        GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1 || echo "未检测到")"
        log_info "GPU: ${GPU_NAME}"
    else
        log_warn "未检测到 nvidia-smi，可能不是 GPU 实例（Whisper 会很慢）"
    fi
    [[ "$(whoami)" == "root" ]] && log_error "禁止以 root 直接执行此脚本，请用 ubuntu 等非 root 用户 SSH 登录" && exit 1

    if command -v apt-get >/dev/null 2>&1; then
        log_info "系统: $(lsb_release -sd 2>/dev/null || cat /etc/os-release 2>/dev/null | grep PRETTY_NAME= | cut -d= -f2 | tr -d '"')"
    fi
}

ensure_os_deps() {
    log_section "安装基础系统依赖（git/curl/wget/ffmpeg/python3 等）"
    local need_update=0
    if ! command -v git >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1 || ! command -v ffmpeg >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
        need_update=1
    fi
    if [[ "$need_update" == "1" ]]; then
        log_info "执行 apt-get update（只在缺失依赖时触发）"
        sudo DEBIAN_FRONTEND=noninteractive apt-get update -y -q || true
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
            git curl wget ca-certificates ffmpeg python3 python3-venv python3-pip supervisor unzip rsync || \
            log_warn "apt 安装部分包失败，继续尝试下一步（HAI 镜像通常已自带）"
    else
        log_success "基础依赖已就绪，跳过 apt-get"
    fi
}

clone_or_pull_repo() {
    log_section "拉取代码仓库"
    if [[ "$LOCAL_MODE" == "1" ]]; then
        log_warn "--local 模式：跳过 git clone，使用当前目录作为项目目录"
        INSTALL_DIR_DEFAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    else
        if [[ -d "${INSTALL_DIR_DEFAULT}/.git" ]]; then
            log_info "检测到旧版安装，尝试 git pull --ff-only 更新..."
            cd "${INSTALL_DIR_DEFAULT}"
            if git pull --ff-only origin "${BRANCH_DEFAULT}"; then
                log_success "仓库已更新到最新 ${BRANCH_DEFAULT}"
            else
                log_warn "git pull --ff-only 失败，请手动 stash/commit 后重新执行脚本"
                exit 1
            fi
        else
            log_info "克隆仓库 ${REPO_DEFAULT}（分支 ${BRANCH_DEFAULT}） -> ${INSTALL_DIR_DEFAULT}"
            git clone --depth 1 --branch "${BRANCH_DEFAULT}" "${REPO_DEFAULT}" "${INSTALL_DIR_DEFAULT}"
            log_success "代码拉取完成"
        fi
    fi

    PROJECT_ROOT="${INSTALL_DIR_DEFAULT}"
    cd "${PROJECT_ROOT}"
}

prepare_dotenv() {
    log_section "预置 .env 模板（HAI 内网镜像源已自动配置）"
    if [[ -f "${PROJECT_ROOT}/.env" ]]; then
        log_info "检测到现有 .env，已保留不覆盖（如需重置，可先备份后删除再重跑脚本）"
    else
        if [[ -f "${PROJECT_ROOT}/.env.example" ]]; then
            cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
            log_success "已从 .env.example 复制空模板 .env（MIRROR_MODE / HF_ENDPOINT / USE_MODELSCOPE 已预填）"
        else
            log_warn "未找到 .env.example，将跳过 .env 预置，稍后安装脚本自行处理"
        fi
    fi
}

run_install() {
    log_section "执行主安装（首次运行约 10~20 分钟，下载 Whisper / TTS 模型 + 虚拟环境 + 前端依赖）"
    cd "${PROJECT_ROOT}"
    if [[ ! -x "${PROJECT_ROOT}/install.sh" ]]; then
        chmod +x "${PROJECT_ROOT}/install.sh" || true
    fi
    log_info "调用 ./install.sh --mirror tencent-intranet（腾讯云内网源最快，失败将自动回退）"
    if ! bash "${PROJECT_ROOT}/install.sh" --mirror tencent-intranet; then
        log_warn "tencent-intranet 镜像失败，尝试回退到 tencent 公网镜像..."
        if ! bash "${PROJECT_ROOT}/install.sh" --mirror tencent; then
            log_warn "tencent 公网也失败，尝试 china 通用镜像..."
            bash "${PROJECT_ROOT}/install.sh" --mirror china
        fi
    fi
    log_success "主安装完成"
}

setup_motd_if_able() {
    log_section "追加 SSH 登录欢迎横幅（MOTD）"
    cd "${PROJECT_ROOT}"
    MOTD_SCRIPT="${PROJECT_ROOT}/scripts/install/setup_motd.sh"
    if [[ ! -x "${MOTD_SCRIPT}" ]]; then
        chmod +x "${MOTD_SCRIPT}" || true
    fi
    if sudo -n true 2>/dev/null; then
        log_info "当前用户有 sudo 免密权限，自动执行 MOTD 追加"
        if sudo bash "${MOTD_SCRIPT}"; then
            log_success "MOTD 欢迎横幅已追加（下次 SSH 登录即可看到）"
        else
            log_warn "MOTD 追加失败（不影响功能），可稍后手动执行：sudo ${MOTD_SCRIPT}"
        fi
    else
        log_warn "当前用户没有免密 sudo（HAI 默认可用 sudo），安装完成后请手动执行："
        echo ""
        echo -e "  ${COLOR_BOLD}sudo ${MOTD_SCRIPT}${COLOR_RESET}"
        echo ""
    fi
}

show_next_steps() {
    log_section "✅ 部署完成！下一步"
    IP_HINT="<实例公网IP>"
    if command -v curl >/dev/null 2>&1; then
        IP_HINT="$(curl -fsSL --max-time 3 http://metadata.tencentyun.com/latest/meta-data/public-ipv4 2>/dev/null || \
                  curl -fsSL --max-time 3 http://169.254.0.23/latest/meta-data/public-ipv4 2>/dev/null || \
                  hostname -I 2>/dev/null | awk '{print $1}' || echo "<实例公网IP>")"
    fi
    cat <<NEXT
┌──────────────────────────────────────────────────────────┐
│ 🌐 访问地址（默认端口，首次访问自动跳转配置页）            │
│                                                           │
│    前端翻译界面：  http://${IP_HINT}:8080              │
│    后端 API 文档： http://${IP_HINT}:8000/docs         │
├──────────────────────────────────────────────────────────┤
│ 🔑 配置 LLM（三选一，选一种就行）                          │
│                                                           │
│   A. Web UI 引导页（新手，推荐）：                         │
│      打开上面的前端地址 → 自动跳到 /setup → 填 3 项       │
│      （Base URL / API Key / Model）→ 勾选立即重启          │
│                                                           │
│   B. SSH 命令行向导：                                     │
│      cd ${PROJECT_ROOT}                                   │
│      ./configure.sh                                       │
│                                                           │
│   C. 手动编辑 .env 后重启：                                │
│      nano ${PROJECT_ROOT}/.env   ← 填 3 件套              │
│      ./manage-supervisor.sh restart                       │
├──────────────────────────────────────────────────────────┤
│ 🧰 日常命令                                               │
│                                                           │
│   服务状态：   ./manage-supervisor.sh status               │
│   查看日志：   ./manage-supervisor.sh tail all             │
│   升级版本：   ./update_project.sh                         │
│   重新配置：   ./configure.sh                              │
└──────────────────────────────────────────────────────────┘
NEXT
    echo ""
    log_info "如果 SSH 刚登录看不到上面的 IP，也可以直接复制下面一行配置 LLM："
    echo -e "  ${COLOR_BOLD}cd ${PROJECT_ROOT} && ./configure.sh${COLOR_RESET}"
    echo ""
}

main() {
    banner
    detect_hai_env
    ensure_os_deps
    clone_or_pull_repo
    prepare_dotenv
    run_install
    setup_motd_if_able
    show_next_steps
    echo ""
    log_success "🎉 全部部署完成！打开 http://<实例公网IP>:8080 开始使用吧"
}

main
