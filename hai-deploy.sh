#!/bin/bash
# ============================================================
# AI 音视频翻译系统 - HAI 一键部署脚本
#
# 用途：用户从作者推广链接 https://curl.qcloud.com/9j4S4Hug
#       购买同款 V100 32GB HAI 实例后，在 HAI 控制台点「Web 终端」
#       或自己 SSH 登录，粘贴下面一行命令即可全自动部署：
#
#   bash -c "$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh)"
#
# 国内加速（ghproxy 代理 GitHub raw）：
#   bash -c "$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh)"
#
# 无 curl 用 wget：
#   wget -O - https://ghproxy.com/https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh | bash
#
# 部署策略（从快到慢，自动 fallback）：
#   1) 有 Docker + Nvidia Runtime → 优先拉 ghcr.io 预打包镜像（3~8 分钟）
#   2) ghcr.io 失败 → 尝试拉 TCR 个人版镜像（HAI 内网极速，2~3 分钟）
#   3) 都失败 → 退回现场编译 install.sh（30~60 分钟，兜底 100% 能成）
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
log_success() { echo -e "${COLOR_GREEN}[ OK ]${COLOR_RESET} $*"; }
log_warn()    { echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $*"; }
log_error()   { echo -e "${COLOR_RED}[ERR ]${COLOR_RESET} $*" >&2; }
log_section() { echo ""; echo -e "${COLOR_BOLD}${COLOR_CYAN}▶ $*${COLOR_RESET}"; echo ""; }

REPO_DEFAULT="https://github.com/icuic/video-voice-translator.git"
BRANCH_DEFAULT="master"
INSTALL_DIR_DEFAULT="${HOME}/video-voice-translator"

# 镜像地址（与 scripts/build_push_images.sh 保持一致）
GHCR_IMAGE_DEFAULT="ghcr.io/icuic/video-voice-translator:latest"
TCR_IMAGE_DEFAULT="ccr.ccs.tencentyun.com/vvt-public/video-voice-translator:latest"

LOCAL_MODE=0
SKIP_DOCKER=0
FORCE_SOURCE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --local)         LOCAL_MODE=1;    shift ;;
        --skip-docker)   SKIP_DOCKER=1;   shift ;;
        --force-source)  FORCE_SOURCE=1;  shift ;;
        --repo)          REPO_DEFAULT="$2";    shift 2 ;;
        --branch)        BRANCH_DEFAULT="$2";  shift 2 ;;
        --dir)           INSTALL_DIR_DEFAULT="$2"; shift 2 ;;
        --ghcr-image)    GHCR_IMAGE_DEFAULT="$2"; shift 2 ;;
        --tcr-image)     TCR_IMAGE_DEFAULT="$2";  shift 2 ;;
        -h|--help)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *) log_error "未知参数: $1"; exit 1 ;;
    esac
done

trap 'log_error "部署中断，第 $LINENO 行，请把上面完整报错截图发作者或提 Issue"' ERR

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
      目标：全自动完成，小白无需任何操作，粘贴一行命令即可
BANNER
}

detect_env() {
    log_section "环境检测"
    if command -v nvidia-smi >/dev/null 2>&1; then
        GPU_NAME="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -n1 || echo "未知GPU")"
        log_success "GPU 已就绪: ${GPU_NAME}"
    else
        log_warn "未检测到 nvidia-smi，若在腾讯云 HAI GPU 实例上运行，可能驱动未安装好（一般官方 PyTorch 基础镜像自带）"
    fi
    if [[ "$(whoami)" == "root" ]]; then
        log_warn "当前是 root 登录，建议后续用非 root 用户管理（部署过程会尽量兼容 root）"
    fi
    log_info "当前用户: $(whoami)    工作目录: ${INSTALL_DIR_DEFAULT}"
}

ensure_os_deps() {
    log_section "安装基础系统依赖（git/curl/wget/ffmpeg/python3/supervisor/docker）"
    local need_update=0
    local missing=""
    for cmd in git curl wget ffmpeg python3 supervisor; do
        command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"
    done
    if [[ -n "$missing" ]]; then
        log_info "缺失依赖: $missing，正在 apt-get 安装..."
        sudo DEBIAN_FRONTEND=noninteractive apt-get update -y -q || true
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
            git curl wget ca-certificates ffmpeg python3 python3-venv python3-pip supervisor unzip rsync || \
            log_warn "apt 部分安装失败，稍后会自动尝试其他方式"
    else
        log_success "基础依赖已就绪"
    fi

    # Docker / docker compose v2 检测：没装就尝试官方脚本安装
    if ! command -v docker >/dev/null 2>&1; then
        log_warn "未检测到 docker，尝试自动安装（仅 ~3 分钟；失败就回退到源码安装）"
        if command -v apt-get >/dev/null 2>&1; then
            (
                set +e
                sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends docker.io docker-compose-v2 2>/dev/null
            ) || true
        fi
        if ! command -v docker >/dev/null 2>&1; then
            log_warn "apt 安装 docker 失败，后续跳过 Docker 路径（不影响功能，只是耗时更长）"
            SKIP_DOCKER=1
        else
            # 免 sudo docker（把当前用户加进 docker 组，重新登录生效；本次部署用 sudo 兜底）
            sudo usermod -aG docker "$(whoami)" 2>/dev/null || true
        fi
    else
        log_success "Docker 已就绪: $(docker -v 2>/dev/null)"
    fi

    # nvidia-container-toolkit 检测（GPU Docker 必需）
    DOCKER_RUNTIME_OK=0
    if command -v docker >/dev/null 2>&1; then
        if sudo docker run --rm --gpus all --runtime=nvidia -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
                nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
            DOCKER_RUNTIME_OK=1
            log_success "Docker GPU Runtime 正常（nvidia-container-toolkit 已配置）"
        elif sudo docker info 2>/dev/null | grep -q nvidia; then
            DOCKER_RUNTIME_OK=1
            log_success "Docker nvidia runtime 已启用"
        else
            log_warn "Docker nvidia 运行时未配置，尝试自动安装..."
            (
                set +e
                curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null
                curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
                    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
                    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null 2>&1
                sudo apt-get update -y -q 2>&1 | tail -3
                sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends nvidia-container-toolkit 2>&1 | tail -5
                sudo nvidia-ctk runtime configure --runtime=docker 2>/dev/null
                sudo systemctl restart docker 2>/dev/null
            ) || log_warn "自动安装 nvidia runtime 失败，跳过 Docker 路径（走源码兜底）"
            # 再检测一次
            if sudo docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
                DOCKER_RUNTIME_OK=1
            else
                SKIP_DOCKER=1
            fi
        fi
    fi
}

clone_or_pull_repo() {
    log_section "获取项目代码"
    if [[ "$LOCAL_MODE" == "1" ]]; then
        log_success "--local 模式：使用当前目录"
        INSTALL_DIR_DEFAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    else
        if [[ -d "${INSTALL_DIR_DEFAULT}/.git" ]]; then
            log_info "已存在老版本，尝试 git pull --ff-only ..."
            cd "${INSTALL_DIR_DEFAULT}"
            if git pull --ff-only origin "${BRANCH_DEFAULT}"; then
                log_success "仓库已更新到最新 ${BRANCH_DEFAULT}"
            else
                log_warn "git pull --ff-only 失败，提示手动 stash 或 commit 后重跑"
                exit 1
            fi
        else
            log_info "git clone --depth 1 ${REPO_DEFAULT} -> ${INSTALL_DIR_DEFAULT}"
            git clone --depth 1 --branch "${BRANCH_DEFAULT}" "${REPO_DEFAULT}" "${INSTALL_DIR_DEFAULT}"
            log_success "代码拉取完成"
        fi
    fi
    PROJECT_ROOT="${INSTALL_DIR_DEFAULT}"
    cd "${PROJECT_ROOT}"
}

prepare_dotenv_and_dirs() {
    log_section "预置 .env 模板 & 数据目录"
    cd "${PROJECT_ROOT}"
    # 镜像宿主机挂载目录（docker-compose 用）
    mkdir -p vvt-data vvt-env
    if [[ -f "${PROJECT_ROOT}/.env" ]]; then
        log_success "已存在 .env，保留不覆盖"
    else
        if [[ -f "${PROJECT_ROOT}/.env.example" ]]; then
            cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
            # Docker 模式下也要把一份 copy 到挂载卷
            cp -n "${PROJECT_ROOT}/.env" "${PROJECT_ROOT}/vvt-env/.env" 2>/dev/null || true
            log_success "已预置 .env（MIRROR_MODE / HF_ENDPOINT / USE_MODELSCOPE 已填好腾讯云默认值）"
        else
            log_warn "未找到 .env.example，跳过预置，后续 .env 会通过 Web /setup 生成"
        fi
    fi
    # 脚本可执行
    chmod +x hai-deploy.sh configure.sh update_project.sh install.sh manage-supervisor.sh 2>/dev/null || true
    find scripts -type f -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
}

deploy_with_docker() {
    log_section "路径 A：使用 Docker 预打包镜像（首选，最快 3~8 分钟）"
    cd "${PROJECT_ROOT}"

    # docker compose v2 是否可用
    local dc="docker compose"
    if ! (docker compose version >/dev/null 2>&1); then
        if command -v docker-compose >/dev/null 2>&1; then
            dc="docker-compose"
        else
            log_warn "docker compose v2 不可用，尝试手动 docker run"
            dc=""
        fi
    fi

    TRY_COUNT=0
    DEPLOY_OK=0

    for IMAGE in "${GHCR_IMAGE_DEFAULT}" "${TCR_IMAGE_DEFAULT}"; do
        TRY_COUNT=$((TRY_COUNT + 1))
        log_info "[$TRY_COUNT/2] 尝试拉取镜像: ${IMAGE}"

        # --- Step 1: pull（带进度，静默除最后几行） --
        local pull_start
        pull_start=$(date +%s)
        if sudo -n true 2>/dev/null; then
            set +e
            sudo docker pull "${IMAGE}" 2>&1 | tail -5
            local rc=${PIPESTATUS[0]}
            set -e
        else
            set +e
            docker pull "${IMAGE}" 2>&1 | tail -5
            local rc=${PIPESTATUS[0]}
            set -e
        fi
        local pull_end
        pull_end=$(date +%s)
        if [[ "$rc" != "0" ]]; then
            log_warn "拉取 ${IMAGE} 失败（耗时 $((pull_end - pull_start))s），尝试下一个镜像源..."
            continue
        fi
        log_success "镜像 ${IMAGE} 拉取成功，耗时 $((pull_end - pull_start))s"

        # --- Step 2: 根据可用工具启动容器 --
        set +e
        if [[ -n "$dc" && -f "${PROJECT_ROOT}/docker-compose.yml" ]]; then
            log_info "使用 docker-compose 启动（docker-compose.yml 已配置端口/卷/GPU）"
            VVT_IMAGE="${IMAGE}" $dc up -d 2>&1 | tail -10
            rc=$?
        else
            log_info "回退 docker run 直接启动"
            sudo docker rm -f vvt 2>/dev/null || true
            sudo docker run -d \
                --name vvt \
                --gpus all \
                --restart unless-stopped \
                -p 8080:8080 -p 8000:8000 -p 5173:5173 \
                -v "${PROJECT_ROOT}/vvt-data:/app/data" \
                -v "${PROJECT_ROOT}/vvt-env:/app/env" \
                --shm-size=8g \
                "${IMAGE}" 2>&1 | tail -5
            rc=$?
        fi
        set -e

        if [[ "$rc" == "0" ]]; then
            DEPLOY_OK=1
            log_success "Docker 容器 vvt 已启动"
            export VVT_DEPLOY_MODE="docker"
            export VVT_RUNTIME_IMAGE="${IMAGE}"
            break
        else
            log_warn "容器启动失败，尝试下一个镜像源..."
        fi
    done

    return "$DEPLOY_OK"
}

deploy_with_source() {
    log_section "路径 B：源码编译安装（兜底，10~30 分钟，100% 成功）"
    cd "${PROJECT_ROOT}"
    log_info "调用 ./install.sh --mirror tencent-intranet（失败自动回退镜像源）"
    if ! bash ./install.sh --mirror tencent-intranet; then
        log_warn "tencent-intranet 失败，回退到 tencent..."
        if ! bash ./install.sh --mirror tencent; then
            log_warn "tencent 失败，回退到 china 通用镜像..."
            bash ./install.sh --mirror china
        fi
    fi
    log_success "源码编译安装完成"

    # 追加 MOTD
    log_info "追加 SSH 登录欢迎横幅（MOTD）..."
    MOTD_SCRIPT="${PROJECT_ROOT}/scripts/install/setup_motd.sh"
    if sudo -n true 2>/dev/null; then
        sudo bash "${MOTD_SCRIPT}" 2>&1 | tail -5 || log_warn "MOTD 追加失败（不影响使用），可稍后手动执行：sudo ${MOTD_SCRIPT}"
    fi
    export VVT_DEPLOY_MODE="source"
}

show_finish() {
    log_section "✅ 部署完成！下一步操作"
    IP_HINT="<实例公网IP>"
    if command -v curl >/dev/null 2>&1; then
        IP_HINT="$(curl -fsSL --max-time 3 http://metadata.tencentyun.com/latest/meta-data/public-ipv4 2>/dev/null || \
                  curl -fsSL --max-time 3 http://169.254.0.23/latest/meta-data/public-ipv4 2>/dev/null || \
                  hostname -I 2>/dev/null | awk '{print $1}' || echo "<实例公网IP>")"
    fi
    cat <<NEXT
┌────────────────────────────────────────────────────────────┐
│ 🎉 部署方式： ${VVT_DEPLOY_MODE:-unknown}
│ 💡 运行镜像： ${VVT_RUNTIME_IMAGE:-源码编译模式}
├────────────────────────────────────────────────────────────┤
│ 🌐 访问地址（首次打开会自动跳到配置页）                       │
│                                                             │
│   前端翻译界面：  http://${IP_HINT}:8080                    │
│   前端备用端口：  http://${IP_HINT}:5173                    │
│   后端 API 文档： http://${IP_HINT}:8000/docs               │
├────────────────────────────────────────────────────────────┤
│ 🔑 配置 LLM（三选一，新手推荐方式 A）                         │
│                                                             │
│   A. 👶 Web UI 引导页（首选）：直接打开上面 8080 地址         │
│      自动跳 /setup → 填 3 项 → 勾选「立即重启」             │
│                                                             │
│   B. 📟 SSH 命令行向导：                                     │
│      cd ${PROJECT_ROOT} && ./configure.sh                   │
│                                                             │
│   C. ✍️  手动编辑 .env：                                      │
│      nano ${PROJECT_ROOT}/.env 填 3 件套 →                  │
│      ./manage-supervisor.sh restart  (源码模式)             │
│      或 sudo docker restart vvt (Docker 模式)               │
├────────────────────────────────────────────────────────────┤
│ 🧰 日常命令（${VVT_DEPLOY_MODE:-docker} 模式）                │
│                                                             │
NEXT
    if [[ "${VVT_DEPLOY_MODE:-docker}" == "docker" ]]; then
        cat <<DOCKERCMDS
│   查看状态：  sudo docker ps | grep vvt                      │
│   查看日志：  sudo docker logs -f vvt                        │
│   重启服务：  sudo docker restart vvt                        │
│   服务停止：  sudo docker stop vvt                           │
│   升级版本：  sudo docker pull ${VVT_RUNTIME_IMAGE_GLOBAL:-ghcr.io/icuic/video-voice-translator:latest}
│                sudo docker rm -f vvt && 重跑本脚本或 compose up -d
DOCKERCMDS
    else
        cat <<SRC
│   状态：     cd ${PROJECT_ROOT} && ./manage-supervisor.sh status
│   日志：     cd ${PROJECT_ROOT} && ./manage-supervisor.sh tail all
│   重启：     cd ${PROJECT_ROOT} && ./manage-supervisor.sh restart
│   升级：     cd ${PROJECT_ROOT} && ./update_project.sh
SRC
    fi
    cat <<FOOT
└────────────────────────────────────────────────────────────┘
FOOT
    echo ""
    log_info "提示：如果刚刚部署完成，首次访问 8080 页面会稍慢（Whisper/TTS 模型预热中，1 分钟内就好）"
    log_info "配置页 /setup 可以随时打开：http://${IP_HINT}:8080/setup"
}

main() {
    banner
    detect_env
    ensure_os_deps
    clone_or_pull_repo
    prepare_dotenv_and_dirs

    # 决定走哪条路径
    DOCKER_OK=0
    if [[ "$FORCE_SOURCE" != "1" && "$SKIP_DOCKER" != "1" && "$DOCKER_RUNTIME_OK" == "1" ]]; then
        set +e
        deploy_with_docker
        DOCKER_OK=$?
        set -e
    fi
    if [[ "$DOCKER_OK" != "1" ]]; then
        deploy_with_source
    fi

    show_finish
    echo ""
    log_success "🎉 全部完成！打开 http://<实例公网IP>:8080 开始使用吧"
}

# 供 show_finish 引用
VVT_RUNTIME_IMAGE_GLOBAL="${GHCR_IMAGE_DEFAULT}"
export VVT_RUNTIME_IMAGE_GLOBAL
main
