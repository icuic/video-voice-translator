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

IS_ROOT=0
if [[ "$(id -u)" -eq 0 ]]; then
    IS_ROOT=1
fi
as_root() {
    if [[ "$IS_ROOT" == "1" ]]; then
        "$@"
    else
        sudo -n "$@" 2>/dev/null || sudo "$@"
    fi
}

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
        as_root env DEBIAN_FRONTEND=noninteractive apt-get update -y -q || true
        as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
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
                as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends docker.io docker-compose-v2 containerd 2>&1 | tail -10
                if command -v systemctl >/dev/null 2>&1; then
                    as_root systemctl enable docker 2>/dev/null || true
                    as_root systemctl start docker 2>/dev/null || true
                else
                    # HAI LXC 环境通常没有 systemd，尝试直接起 dockerd
                    if [[ ! -S /var/run/docker.sock ]]; then
                        as_root mkdir -p /var/run /var/lib/docker /var/log
                        as_root /usr/bin/dockerd --storage-driver=overlay2 \
                            --iptables=false --ip-masq=false --bridge=none \
                            --pidfile=/tmp/dockerd-deploy.pid \
                            > /tmp/dockerd-deploy.log 2>&1 &
                        sleep 5
                    fi
                fi
                sleep 2
            ) || true
        fi
        if ! command -v docker >/dev/null 2>&1; then
            log_warn "apt 安装 docker 失败，后续跳过 Docker 路径（不影响功能，只是耗时更长）"
            SKIP_DOCKER=1
        else
            # 免 sudo docker（把当前用户加进 docker 组，重新登录生效；本次部署用 sudo 兜底）
            if [[ "$IS_ROOT" != "1" ]]; then
                as_root usermod -aG docker "$(whoami)" 2>/dev/null || true
            fi
            # 统一：当前用户无 docker 权限时统一加 as_root（部署期间免重新登录）
            if ! (docker info >/dev/null 2>&1); then
                if ! (as_root docker info >/dev/null 2>&1); then
                    # 若 as_root 也连不上（daemon 没起来），尝试重启
                    if command -v systemctl >/dev/null 2>&1; then
                        as_root systemctl restart docker 2>/dev/null || true
                    elif [[ ! -S /var/run/docker.sock ]]; then
                        as_root mkdir -p /var/run /var/lib/docker /var/log
                        as_root pkill -9 dockerd 2>/dev/null || true
                        sleep 1
                        as_root /usr/bin/dockerd --storage-driver=overlay2 \
                            --iptables=false --ip-masq=false --bridge=none \
                            --pidfile=/tmp/dockerd-deploy.pid \
                            > /tmp/dockerd-deploy.log 2>&1 &
                        sleep 5
                    fi
                    sleep 3
                fi
            fi
        fi
    else
        log_success "Docker 已就绪: $(docker -v 2>/dev/null)"
    fi

    # nvidia-container-toolkit 检测（GPU Docker 必需）
    DOCKER_RUNTIME_OK=0
    if command -v docker >/dev/null 2>&1; then
        local docker_test_cmd
        if (docker info >/dev/null 2>&1); then
            docker_test_cmd="docker"
        else
            docker_test_cmd="as_root docker"
        fi
        if $docker_test_cmd run --rm --gpus all --runtime=nvidia -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
                nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
            DOCKER_RUNTIME_OK=1
            log_success "Docker GPU Runtime 正常（nvidia-container-toolkit 已配置）"
        elif $docker_test_cmd info 2>/dev/null | grep -q nvidia; then
            DOCKER_RUNTIME_OK=1
            log_success "Docker nvidia runtime 已启用"
        else
            log_warn "Docker nvidia 运行时未配置，尝试自动安装..."
            (
                set +e
                curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | as_root gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null
                curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
                    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
                    as_root tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null 2>&1
                as_root env DEBIAN_FRONTEND=noninteractive apt-get update -y -q 2>&1 | tail -3
                as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends nvidia-container-toolkit 2>&1 | tail -5
                as_root nvidia-ctk runtime configure --runtime=docker 2>/dev/null
                if command -v systemctl >/dev/null 2>&1; then
                    as_root systemctl restart docker 2>/dev/null
                else
                    as_root pkill -HUP dockerd 2>/dev/null || true
                fi
                sleep 3
            ) || log_warn "自动安装 nvidia runtime 失败，跳过 Docker 路径（走源码兜底）"
            # 再检测一次
            if $docker_test_cmd run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
                DOCKER_RUNTIME_OK=1
            else
                log_warn "nvidia runtime 仍不可用，尝试跳过 runtime 检测直接判断 nvidia-ctk 是否已安装..."
                if command -v nvidia-ctk >/dev/null 2>&1 || command -v nvidia-container-cli >/dev/null 2>&1; then
                    DOCKER_RUNTIME_OK=1
                    log_success "nvidia-container-toolkit 已安装，假设 Docker GPU 可用（跳过 pull 验证节省时间）"
                else
                    SKIP_DOCKER=1
                fi
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

    run_docker() {
        if (docker info >/dev/null 2>&1); then
            docker "$@"
        else
            as_root docker "$@"
        fi
    }
    run_compose() {
        if (docker info >/dev/null 2>&1); then
            docker compose "$@"
        else
            as_root docker compose "$@"
        fi
    }

    # docker compose v2 是否可用
    local dc_available=1
    if ! (run_compose version >/dev/null 2>&1); then
        if command -v docker-compose >/dev/null 2>&1; then
            DOCKER_COMPOSE_BIN="docker-compose"
            if ! (docker-compose version >/dev/null 2>&1) && ! (docker info >/dev/null 2>&1); then
                DOCKER_COMPOSE_BIN="as_root docker-compose"
            fi
        else
            log_warn "docker compose v2 不可用，尝试手动 docker run"
            dc_available=0
        fi
    fi

    # 智能选择镜像拉取源：国内网络自动加 ghproxy 镜像代理
    local GHCR_MIRROR=""
    if [[ -z "${GHCR_MIRROR:-}" ]] && command -v curl >/dev/null 2>&1; then
        if ! (curl -fsSL --max-time 5 https://ghcr.io >/dev/null 2>&1); then
            if (curl -fsSL --max-time 5 https://ghcr.dockerproxy.com >/dev/null 2>&1); then
                GHCR_MIRROR="ghcr.dockerproxy.com"
            elif (curl -fsSL --max-time 5 https://docker.1ms.run >/dev/null 2>&1); then
                GHCR_MIRROR="docker.1ms.run"
            fi
        fi
    fi
    local GHCR_IMAGE_RESOLVED="${GHCR_IMAGE_DEFAULT}"
    if [[ -n "${GHCR_MIRROR}" && "${GHCR_IMAGE_DEFAULT}" == ghcr.io/* ]]; then
        GHCR_IMAGE_RESOLVED="${GHCR_MIRROR}/${GHCR_IMAGE_DEFAULT#ghcr.io/}"
        log_info "ghcr.io 直连可能较慢，自动使用镜像代理 ${GHCR_MIRROR}（实际拉取 ${GHCR_IMAGE_RESOLVED}，成功后 retag 为 ${GHCR_IMAGE_DEFAULT}）"
    fi

    TRY_COUNT=0
    DEPLOY_OK=0
    declare -a IMAGE_CANDIDATES=()
    IMAGE_CANDIDATES+=("${TCR_IMAGE_DEFAULT}")
    IMAGE_CANDIDATES+=("${GHCR_IMAGE_RESOLVED}")
    if [[ "${GHCR_IMAGE_RESOLVED}" != "${GHCR_IMAGE_DEFAULT}" ]]; then
        IMAGE_CANDIDATES+=("${GHCR_IMAGE_DEFAULT}")
    fi

    for IMAGE in "${IMAGE_CANDIDATES[@]}"; do
        TRY_COUNT=$((TRY_COUNT + 1))
        log_info "[$TRY_COUNT/${#IMAGE_CANDIDATES[@]}] 尝试拉取镜像: ${IMAGE}"

        local pull_start
        pull_start=$(date +%s)
        set +e
        run_docker pull "${IMAGE}" 2>&1 | tail -10
        local rc=${PIPESTATUS[0]}
        set -e
        local pull_end
        pull_end=$(date +%s)
        if [[ "$rc" != "0" ]]; then
            log_warn "拉取 ${IMAGE} 失败（耗时 $((pull_end - pull_start))s），尝试下一个镜像源..."
            continue
        fi
        log_success "镜像 ${IMAGE} 拉取成功，耗时 $((pull_end - pull_start))s"

        # 如果用了 ghcr 镜像代理，retag 回标准名字，方便 docker-compose.yml 里默认值匹配
        local EFFECTIVE_IMAGE="${IMAGE}"
        if [[ "${IMAGE}" == "${GHCR_IMAGE_RESOLVED}" && "${GHCR_IMAGE_RESOLVED}" != "${GHCR_IMAGE_DEFAULT}" ]]; then
            run_docker tag "${IMAGE}" "${GHCR_IMAGE_DEFAULT}" 2>/dev/null || true
            EFFECTIVE_IMAGE="${GHCR_IMAGE_DEFAULT}"
        fi

        # --- Step 2: 根据可用工具启动容器 --
        set +e
        if [[ "$dc_available" == "1" && -f "${PROJECT_ROOT}/docker-compose.yml" ]]; then
            log_info "使用 docker-compose 启动（docker-compose.yml 已配置端口/卷/GPU）"
            VVT_IMAGE="${EFFECTIVE_IMAGE}" run_compose up -d 2>&1 | tail -15
            rc=$?
        else
            log_info "回退 docker run 直接启动"
            run_docker rm -f vvt 2>/dev/null || true
            run_docker run -d \
                --name vvt \
                --gpus all \
                --restart unless-stopped \
                -p 8080:8080 -p 8000:8000 -p 5173:5173 \
                -v "${PROJECT_ROOT}/vvt-data:/app/data" \
                -v "${PROJECT_ROOT}/vvt-env:/app/env" \
                --shm-size=8g \
                "${EFFECTIVE_IMAGE}" 2>&1 | tail -10
            rc=$?
        fi
        set -e

        if [[ "$rc" == "0" ]]; then
            DEPLOY_OK=1
            log_success "Docker 容器 vvt 已启动"
            export VVT_DEPLOY_MODE="docker"
            export VVT_RUNTIME_IMAGE="${EFFECTIVE_IMAGE}"
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
    if [[ "$IS_ROOT" == "1" ]]; then
        bash "${MOTD_SCRIPT}" 2>&1 | tail -5 || log_warn "MOTD 追加失败（不影响使用），可稍后手动执行：bash ${MOTD_SCRIPT}"
    elif sudo -n true 2>/dev/null; then
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

    local MODE="${VVT_DEPLOY_MODE:-unknown}"
    local FRONTEND_PRIMARY_PORT="5173"
    local FRONTEND_BACKUP_PORT=""
    if [[ "${MODE}" == "docker" ]]; then
        FRONTEND_PRIMARY_PORT="8080"
        FRONTEND_BACKUP_PORT="5173"
    else
        FRONTEND_PRIMARY_PORT="5173"
        FRONTEND_BACKUP_PORT=""
    fi
    local PRIMARY_URL="http://${IP_HINT}:${FRONTEND_PRIMARY_PORT}"
    local DOCKER_PREFIX=""
    if (docker info >/dev/null 2>&1); then
        DOCKER_PREFIX="docker"
    else
        DOCKER_PREFIX="as_root docker"
    fi

    cat <<NEXT
┌────────────────────────────────────────────────────────────┐
│ 🎉 部署方式： ${MODE}
│ 💡 运行镜像： ${VVT_RUNTIME_IMAGE:-源码编译模式}
├────────────────────────────────────────────────────────────┤
│ 🌐 访问地址（首次打开会自动跳到配置页）                       │
│                                                             │
NEXT
    if [[ "${MODE}" == "docker" ]]; then
        cat <<DOCKER_ADDR
│   前端翻译界面：  http://${IP_HINT}:8080   （首选，静态预览）   │
│   前端备用端口：  http://${IP_HINT}:5173   （dev server）     │
DOCKER_ADDR
    else
        cat <<SRC_ADDR
│   前端翻译界面：  http://${IP_HINT}:5173   （vite dev）       │
SRC_ADDR
    fi
    cat <<NEXT2
│   后端 API 文档： http://${IP_HINT}:8000/docs               │
├────────────────────────────────────────────────────────────┤
│ 🔑 配置 LLM（三选一，新手推荐方式 A）                         │
│                                                             │
│   A. 👶 Web UI 引导页（首选）：直接打开上面 ${FRONTEND_PRIMARY_PORT} 地址
│      自动跳 /setup → 填 3 项 → 勾选「立即重启」             │
│                                                             │
│   B. 📟 SSH 命令行向导：                                     │
│      cd ${PROJECT_ROOT} && ./configure.sh                   │
│                                                             │
│   C. ✍️  手动编辑 .env：                                      │
│      nano ${PROJECT_ROOT}/.env 填 3 件套 →                  │
NEXT2
    if [[ "${MODE}" == "docker" ]]; then
        cat <<DOCKER_RESTART
│      ${DOCKER_PREFIX} restart vvt  (Docker 模式)            │
DOCKER_RESTART
    else
        cat <<SRC_RESTART
│      ./manage-supervisor.sh restart  (源码模式)             │
SRC_RESTART
    fi

    cat <<NEXT3
├────────────────────────────────────────────────────────────┤
│ 🧰 日常命令（${MODE} 模式）                                  │
│                                                             │
NEXT3
    if [[ "${MODE}" == "docker" ]]; then
        cat <<DOCKERCMDS
│   查看状态：  ${DOCKER_PREFIX} ps | grep vvt                │
│   查看日志：  ${DOCKER_PREFIX} logs -f vvt                  │
│   重启服务：  ${DOCKER_PREFIX} restart vvt                  │
│   服务停止：  ${DOCKER_PREFIX} stop vvt                     │
│   升级版本：  ${DOCKER_PREFIX} pull ${VVT_RUNTIME_IMAGE_GLOBAL:-ghcr.io/icuic/video-voice-translator:latest}
│                ${DOCKER_PREFIX} rm -f vvt && 重跑本脚本或 compose up -d
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
    log_info "提示：如果刚刚部署完成，首次访问 ${FRONTEND_PRIMARY_PORT} 页面会稍慢（Whisper/TTS 模型预热中，1 分钟内就好）"
    log_info "配置页 /setup 可以随时打开：${PRIMARY_URL}/setup"
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
    local FINAL_PORT="5173"
    if [[ "${VVT_DEPLOY_MODE:-}" == "docker" ]]; then
        FINAL_PORT="8080"
    fi
    log_success "🎉 全部完成！打开 http://<实例公网IP>:${FINAL_PORT} 开始使用吧"
}

# 供 show_finish 引用
VVT_RUNTIME_IMAGE_GLOBAL="${GHCR_IMAGE_DEFAULT}"
export VVT_RUNTIME_IMAGE_GLOBAL
main
