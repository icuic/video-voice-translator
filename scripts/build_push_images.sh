#!/bin/bash
# ============================================================
# AI 音视频翻译系统 - 作者专用 Docker 镜像构建 & 推送脚本
#
# 用法：
#   # 1) 准备凭据（只需做一次）
#        GitHub Token (PAT)：有 write:packages 权限 -> export GHCR_TOKEN=xxx
#        TCR 个人版用户名/密码：export TCR_USER=xxx TCR_PASS=xxx TCR_NS=xxx TCR_REGION=ap-guangzhou
#
#   # 2) 构建并打多个 tag
#        ./scripts/build_push_images.sh v1.0.0        # 构建 + 同时推 ghcr.io + TCR
#        ./scripts/build_push_images.sh v1.0.0 --local-only   # 只构建本地镜像，不推送
#        ./scripts/build_push_images.sh v1.0.0 --skip-tcr      # 跳过 TCR，只推 ghcr.io（推荐新手省事儿）
#        ./scripts/build_push_images.sh v1.0.0 --skip-ghcr     # 跳过 ghcr.io，只推 TCR
#
# 前置要求：
#   - Docker 19.03+ （支持 BuildKit）
#   - nvidia-docker（GPU 驱动已装，HAI 默认自带）
#   - 当前实例上已经完整跑过 install.sh，index-tts/.venv + checkpoints 已经在本地
#   - 前端 build 过（dist 目录存在，否则 Dockerfile Stage 1 现场 build 也行）
#
# 镜像体积估算：~15-18GB（.venv 9G + checkpoints 11G，层压缩后）
# ============================================================

set -euo pipefail

COLOR_BOLD='\033[1m'
COLOR_GREEN='\033[32m'
COLOR_YELLOW='\033[33m'
COLOR_RED='\033[31m'
COLOR_CYAN='\033[36m'
COLOR_RESET='\033[0m'

log_info()    { echo -e "${COLOR_CYAN}[build]${COLOR_RESET} $*"; }
log_ok()      { echo -e "${COLOR_GREEN}[OK] ${COLOR_RESET} $*"; }
log_warn()    { echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $*"; }
log_error()   { echo -e "${COLOR_RED}[ERR]${COLOR_RESET} $*" >&2; }
log_section() { echo ""; echo -e "${COLOR_BOLD}${COLOR_CYAN}▶ $*${COLOR_RESET}"; echo ""; }

# ---- 参数解析 ----
if [[ $# -lt 1 ]]; then
    cat <<'HELP'
用法: ./scripts/build_push_images.sh <VERSION> [--local-only] [--skip-tcr] [--skip-ghcr]
  <VERSION>            版本号，如 v1.0.0
  --local-only         只构建本地镜像，不推送任何远端
  --skip-tcr           跳过腾讯云 TCR（只推 ghcr.io）
  --skip-ghcr          跳过 ghcr.io（只推 TCR）
HELP
    exit 1
fi

VERSION="$1"; shift
SKIP_TCR=0
SKIP_GHCR=0
LOCAL_ONLY=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --local-only) LOCAL_ONLY=1; shift ;;
        --skip-tcr)   SKIP_TCR=1;   shift ;;
        --skip-ghcr)  SKIP_GHCR=1;  shift ;;
        -h|--help)    sed -n '2,18p' "$0"; exit 0 ;;
        *)            log_error "未知参数: $1"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# ---- 默认镜像元数据（改这里为你的实际信息） ----
GHCR_IMAGE_BASE="${GHCR_IMAGE_BASE:-ghcr.io/icuic/video-voice-translator}"
TCR_IMAGE_BASE="${TCR_IMAGE_BASE:-ccr.ccs.tencentyun.com/${TCR_NS:-vvt-public}/video-voice-translator}"
TCR_REGION="${TCR_REGION:-ap-guangzhou}"

# ---- 环境检查 ----
log_section "环境检查"
if ! command -v docker >/dev/null 2>&1; then
    log_warn "未检测到 docker，尝试自动通过 apt 安装（当前 HAI PyTorch 基础镜像通常自带，如未自带则需 ~3 分钟）..."
    set +e
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -y -q 2>&1 | tail -3
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
        docker.io docker-compose-v2 containerd nvidia-container-toolkit 2>&1 | tail -10
    set -e
    if command -v docker >/dev/null 2>&1; then
        sudo systemctl enable docker 2>/dev/null || true
        sudo systemctl restart docker 2>/dev/null || true
        sudo usermod -aG docker "$(whoami)" 2>/dev/null || true
        log_ok "Docker 已自动安装: $(docker -v 2>/dev/null)"
        log_warn "注意：usermod 加 docker 组需要重新登录生效，本次 build 命令全部加 sudo 兜底"
    else
        log_error "自动安装 docker 失败，请手动执行：sudo apt-get install -y docker.io docker-compose-v2 nvidia-container-toolkit"
        exit 1
    fi
fi
# 再兜底测一次 sudo docker 可用（免重新登录）
if ! (sudo docker info >/dev/null 2>&1); then
    log_warn "sudo docker info 无法连接 docker daemon..."
    # HAI 实例很可能没有真正的 systemd (dumb-init/LXC 容器环境)，systemctl restart 没用，直接手动起 dockerd
    log_info "尝试直接手动启动 dockerd（自动按 overlay2→fuse→vfs 顺序试 storage driver）..."
    declare -a DOCKERD_STORAGE_ARGS=()
    DOCKERD_LAUNCHED=0
    for sd in overlay2 fuse-overlayfs vfs; do
        DOCKERD_STORAGE_ARGS=(--storage-driver="$sd")
        log_info "  试 storage-driver=$sd ..."
        sudo mkdir -p /var/run /var/lib/docker /var/log
        # 如果之前残留了 pid/socket，先清掉
        sudo rm -f /var/run/docker.pid /var/run/docker.sock /tmp/dockerd.pid 2>/dev/null || true
        sudo pkill -9 dockerd 2>/dev/null || true
        sleep 1
        # 后台起 dockerd，禁用网络栈相关组件（不需要 bridge/iptables/ip-masq 避免 LXC 嵌套权限不足）
        sudo /usr/bin/dockerd "${DOCKERD_STORAGE_ARGS[@]}" \
            --iptables=false --ip-masq=false --bridge=none \
            --pidfile=/tmp/dockerd.pid \
            > /tmp/dockerd-build.log 2>&1 &
        DOCKERD_PID=$!
        THIS_OK=0
        # 等 16 秒看 socket 出不出来
        for i in $(seq 1 20); do
            sleep 1
            if [[ -S /var/run/docker.sock ]]; then
                if (sudo docker info >/dev/null 2>&1); then
                    THIS_OK=1
                    DOCKERD_LAUNCHED=1
                    log_ok "dockerd 手动启动成功 (storage-driver=$sd, pid=$DOCKERD_PID)"
                    break 2
                fi
            fi
            # 进程没了说明起失败了，试下一个 driver
            if ! (sudo kill -0 "$DOCKERD_PID" 2>/dev/null); then
                break
            fi
        done
        # 本轮失败才杀残留；成功就保留后台 daemon 继续用
        if [[ "$THIS_OK" != "1" ]]; then
            sudo kill -9 "$DOCKERD_PID" 2>/dev/null || true
            wait "$DOCKERD_PID" 2>/dev/null || true
        fi
    done
    # 最后再试一次 info
    sleep 2
    if [[ "$DOCKERD_LAUNCHED" != "1" ]] && ! (sudo docker info >/dev/null 2>&1); then
        log_error "Docker daemon 仍不可用，请手动查看 /tmp/dockerd-build.log 排查；也可以跳过 build，用户仍可通过 hai-deploy.sh 走源码安装路径（10~20 分钟出页，功能不打折，只是首次部署稍慢）。"
        exit 1
    fi
fi
# nvidia 运行时可用就不报错，build 阶段可以走 CPU-only（镜像体积稍大但功能一致）
if sudo docker info 2>/dev/null | grep -q nvidia; then
    log_ok "Docker nvidia runtime 已就绪"
else
    log_warn "未检测到 nvidia runtime，将用常规运行时构建镜像（用户 HAI 实例端运行时仍需 GPU）"
fi
for DIR in index-tts/.venv index-tts/checkpoints; do
    if [[ ! -d "${PROJECT_ROOT}/${DIR}" ]]; then
        log_error "目录 ${PROJECT_ROOT}/${DIR} 不存在，必须先运行 ./install.sh 下载模型和 .venv"
        exit 1
    fi
done
SIZE_VENV=$(du -sh "${PROJECT_ROOT}/index-tts/.venv" | awk '{print $1}')
SIZE_CKPT=$(du -sh "${PROJECT_ROOT}/index-tts/checkpoints" | awk '{print $1}')
log_info ".venv = ${SIZE_VENV},  checkpoints = ${SIZE_CKPT}"

# ---- 1.5) 统一 docker 调用：若普通 docker 连不上 daemon，则自动加 sudo ----
#      HAI 默认 ubuntu 用户不在 docker 组，usermod 要重登录生效，build 期间直接 sudo 最稳。
DOCKER_SUDO=""
if ! (docker info >/dev/null 2>&1); then
    if (sudo -n docker info >/dev/null 2>&1); then
        DOCKER_SUDO="sudo"
        log_info "当前用户无 docker 权限，自动改用 sudo docker"
    fi
fi
run_docker() {
    if [[ -n "$DOCKER_SUDO" ]]; then
        $DOCKER_SUDO docker "$@"
    else
        docker "$@"
    fi
}

# ---- 1) Dockerfile 语法预检查（快速失败） ----
log_section "Dockerfile 语法预检"
if command -v hadolint >/dev/null 2>&1; then
    hadolint Dockerfile || log_warn "hadolint 有 lint 告警，忽略继续"
fi
log_ok "Dockerfile 文件就绪"

# ---- 2) 构建镜像 ----
log_section "开始构建镜像 version=${VERSION}（预计 15~30 分钟，取决于 IO 速度）"
TMP_TAG="vvt:build-${VERSION}-$(date +%s)"
export DOCKER_BUILDKIT=1
export BUILDKIT_PROGRESS=plain

run_docker build \
    --file Dockerfile \
    --tag "${TMP_TAG}" \
    --build-arg "BUILD_VERSION=${VERSION}" \
    --progress=plain \
    "${PROJECT_ROOT}" 2>&1 | tail -60

log_ok "本地镜像构建完成: ${TMP_TAG}"

# ---- 3) 打额外 tag（latest + 版本号） ----
log_section "打 tag"
declare -a TAGS=("${VERSION}" "latest")
for t in "${TAGS[@]}"; do
    run_docker tag "${TMP_TAG}" "${GHCR_IMAGE_BASE}:${t}"
    log_ok "本地 tag: ${GHCR_IMAGE_BASE}:${t}"
    if [[ "$SKIP_TCR" != "1" ]]; then
        run_docker tag "${TMP_TAG}" "${TCR_IMAGE_BASE}:${t}"
        log_ok "本地 tag: ${TCR_IMAGE_BASE}:${t}"
    fi
done

if [[ "$LOCAL_ONLY" == "1" ]]; then
    log_ok "--local-only 指定，跳过推送，本地镜像如下："
    run_docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}" \
        | grep -E "(icuic/video-voice|${TCR_NS:-vvt-public}|vvt:build)" | head -15
    exit 0
fi

# ---- 4A) Push ghcr.io ----
if [[ "$SKIP_GHCR" != "1" ]]; then
    log_section "推送至 GitHub Container Registry（ghcr.io）"
    if [[ -z "${GHCR_TOKEN:-}" ]]; then
        log_warn "GHCR_TOKEN 环境变量为空，跳过 ghcr.io 登录（假设已 docker login ghcr.io）"
    else
        echo "${GHCR_TOKEN}" | run_docker login ghcr.io -u "${GHCR_USER:-icuic}" --password-stdin
        log_ok "ghcr.io 登录成功"
    fi
    for t in "${TAGS[@]}"; do
        log_info "push ghcr.io :${t}"
        run_docker push "${GHCR_IMAGE_BASE}:${t}" 2>&1 | tail -10
        log_ok "✅ ${GHCR_IMAGE_BASE}:${t}"
    done
fi

# ---- 4B) Push TCR 个人版 ----
if [[ "$SKIP_TCR" != "1" ]]; then
    log_section "推送至腾讯云容器镜像服务 TCR 个人版（${TCR_REGION}）"
    if [[ -z "${TCR_USER:-}" || -z "${TCR_PASS:-}" ]]; then
        log_warn "TCR_USER / TCR_PASS 未通过 env 注入，跳过登录（假设已 docker login ccr.ccs.tencentyun.com）"
    else
        echo "${TCR_PASS}" | run_docker login ccr.ccs.tencentyun.com -u "${TCR_USER}" --password-stdin
        log_ok "TCR 登录成功"
    fi
    for t in "${TAGS[@]}"; do
        log_info "push TCR :${t}"
        run_docker push "${TCR_IMAGE_BASE}:${t}" 2>&1 | tail -10
        log_ok "✅ ${TCR_IMAGE_BASE}:${t}"
    done
fi

# ---- 5) 摘要 ----
log_section "✅ 构建 & 推送完成"
echo ""
echo "  版本号: ${VERSION}"
echo "  本地标签: ${TMP_TAG}"
if [[ "$SKIP_GHCR" != "1" ]]; then
    echo "  ghcr.io  : ${GHCR_IMAGE_BASE}:${VERSION}   (用户 Docker 免费首选)"
fi
if [[ "$SKIP_TCR" != "1" ]]; then
    echo "  TCR(内网): ${TCR_IMAGE_BASE}:${VERSION}   (HAI 内网拉取，2~3分钟)"
fi
echo ""
echo "  小白部署入口命令（可复制到文档/Web 终端）:"
echo "    bash -c \"\$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh)\""
echo ""
