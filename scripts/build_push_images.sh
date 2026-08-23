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

# ---- 并发互斥锁：同一时间只允许跑 1 份 build_push_images.sh（防止把 vfs storage 写坏） ----
LOCK_FILE="/tmp/vvt-build_push_images.lock"
cleanup_lock() { rm -f "${LOCK_FILE}" 2>/dev/null || true; }
acquire_lock() {
    if [ -e "${LOCK_FILE}" ]; then
        OLD_PID=$(cat "${LOCK_FILE}" 2>/dev/null || true)
        if [ -n "${OLD_PID}" ] && [ -d "/proc/${OLD_PID}" ] 2>/dev/null; then
            OLD_CMD=$(ps -o args= -p "${OLD_PID}" 2>/dev/null | head -c 200 || true)
            echo -e "${COLOR_RED}[ERR]${COLOR_RESET} 检测到另一份 build_push_images.sh 正在运行！（PID=${OLD_PID}）" >&2
            echo -e "      启动命令: ${OLD_CMD}" >&2
            echo -e "      如果确定是僵尸进程，先手动 kill ${OLD_PID}，或者删除 ${LOCK_FILE} 再启动。" >&2
            exit 1
        fi
        echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} 发现旧的 lock 文件（PID=${OLD_PID} 已不存在），自动清理后继续。"
        rm -f "${LOCK_FILE}"
    fi
    echo $$ > "${LOCK_FILE}"
    trap cleanup_lock EXIT INT TERM HUP
}
acquire_lock

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
    as_root env DEBIAN_FRONTEND=noninteractive apt-get update -y -q 2>&1 | tail -3
    as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
        docker.io docker-compose-v2 containerd nvidia-container-toolkit 2>&1 | tail -10
    set -e
    if command -v docker >/dev/null 2>&1; then
        if command -v systemctl >/dev/null 2>&1; then
            as_root systemctl enable docker 2>/dev/null || true
            as_root systemctl restart docker 2>/dev/null || true
        fi
        if [[ "$IS_ROOT" != "1" ]]; then
            as_root usermod -aG docker "$(whoami)" 2>/dev/null || true
        fi
        log_ok "Docker 已自动安装: $(docker -v 2>/dev/null)"
        log_warn "注意：usermod 加 docker 组需要重新登录生效，本次 build 命令全部加 as_root 兜底"
    else
        log_error "自动安装 docker 失败，请手动执行：apt-get install -y docker.io docker-compose-v2 nvidia-container-toolkit"
        exit 1
    fi
fi
# 构建统一的 docker 命令前缀（智能加不加 as_root）
if (docker info >/dev/null 2>&1); then
    DOCKER_RUN_PREFIX=""
else
    DOCKER_RUN_PREFIX="as_root"
fi
run_docker() {
    if [[ -n "$DOCKER_RUN_PREFIX" ]]; then
        $DOCKER_RUN_PREFIX docker "$@"
    else
        docker "$@"
    fi
}
# 再兜底测一次可用
if ! (run_docker info >/dev/null 2>&1); then
    log_warn "run_docker info 无法连接 docker daemon..."
    # HAI 实例很可能没有真正的 systemd (dumb-init/LXC 容器环境)，systemctl restart 没用，直接手动起 dockerd
    log_info "尝试直接手动启动 dockerd（自动按 overlay2→fuse→vfs 顺序试 storage driver）..."
    declare -a DOCKERD_STORAGE_ARGS=()
    DOCKERD_LAUNCHED=0
    for sd in overlay2 fuse-overlayfs vfs; do
        DOCKERD_STORAGE_ARGS=(--storage-driver="$sd")
        log_info "  试 storage-driver=$sd ..."
        as_root mkdir -p /var/run /var/lib/docker /var/log
        # 如果之前残留了 pid/socket，先清掉
        as_root rm -f /var/run/docker.pid /var/run/docker.sock /tmp/dockerd.pid 2>/dev/null || true
        as_root pkill -9 dockerd 2>/dev/null || true
        sleep 1
        # 后台起 dockerd，禁用网络栈相关组件（不需要 bridge/iptables/ip-masq 避免 LXC 嵌套权限不足）
        as_root /usr/bin/dockerd "${DOCKERD_STORAGE_ARGS[@]}" \
            --iptables=false --ip-masq=false --bridge=none \
            --pidfile=/tmp/dockerd.pid \
            > /tmp/dockerd-build.log 2>&1 &
        DOCKERD_PID=$!
        THIS_OK=0
        # 等 16 秒看 socket 出不出来
        for i in $(seq 1 20); do
            sleep 1
            if [[ -S /var/run/docker.sock ]]; then
                if (run_docker info >/dev/null 2>&1); then
                    THIS_OK=1
                    DOCKERD_LAUNCHED=1
                    log_ok "dockerd 手动启动成功 (storage-driver=$sd, pid=$DOCKERD_PID)"
                    break 2
                fi
            fi
            # 进程没了说明起失败了，试下一个 driver
            if ! (as_root kill -0 "$DOCKERD_PID" 2>/dev/null); then
                break
            fi
        done
        # 本轮失败才杀残留；成功就保留后台 daemon 继续用
        if [[ "$THIS_OK" != "1" ]]; then
            as_root kill -9 "$DOCKERD_PID" 2>/dev/null || true
            wait "$DOCKERD_PID" 2>/dev/null || true
        fi
    done
    # 最后再试一次 info
    sleep 2
    if [[ "$DOCKERD_LAUNCHED" != "1" ]] && ! (run_docker info >/dev/null 2>&1); then
        log_error "Docker daemon 仍不可用，请手动查看 /tmp/dockerd-build.log 排查；也可以跳过 build，用户仍可通过 hai-deploy.sh 走源码安装路径（10~20 分钟出页，功能不打折，只是首次部署稍慢）。"
        exit 1
    fi
fi
# nvidia 运行时可用就不报错，build 阶段可以走 CPU-only（镜像体积稍大但功能一致）
if run_docker info 2>/dev/null | grep -q nvidia; then
    log_ok "Docker nvidia runtime 已就绪"
else
    log_warn "未检测到 nvidia runtime，将用常规运行时构建镜像（用户 HAI 实例端运行时仍需 GPU）"
fi
# ---- 1.1.4.1) vfs storage 元数据一致性自检（非常关键！） ----
#      前几次 build crash / kill 后，常见「image 元数据库记录了某 chainID 的 parent，但 /var/lib/docker/vfs/dir/<hash> 被手动删了」→ 报：
#        failed to create rwlayer: <hash>: stat /var/lib/docker/vfs/dir/<hash>: no such file or directory
#      解决：docker images -a 时如果 stderr 出现任何 'stat vfs/dir' / 'no such file or directory' →
#            或者 docker build 首次 Using cache 时就会炸 → 我们在这里检测并主动 wipe 掉脏 storage 重启 daemon。
ensure_vfs_storage_clean() {
    local images_err docker_info_sd
    docker_info_sd=$(run_docker info 2>/dev/null | grep -i "Storage Driver" | head -1 | awk -F: '{print $2}' | xargs || true)
    log_info "Storage Driver 检测: ${docker_info_sd:-unknown}"
    if [[ "${docker_info_sd}" != "vfs" ]]; then
        # 非 vfs 不用管这个问题（overlay2 自己有 GC）
        return 0
    fi
    # 用 docker images -a（会走 vfs graphdriver 校验所有镜像层元数据）测一次
    images_err=$(run_docker images -a >/dev/null 2>&1; echo "") || true
    images_err=$(run_docker images -a 2>&1 >/dev/null | tr -d '\r' || true)
    if [[ -n "${images_err}" ]] && (echo "${images_err}" | grep -qE "stat .*vfs/dir|no such file or directory|failed to create rwlayer"); then
        log_warn "检测到 vfs storage 元数据损坏（之前 build 崩溃留下的脏层）：${images_err}"
        log_info "正在自动清理 /var/lib/docker/{image,vfs,tmp,tmp-old,buildkit,containers,network} + 重启 dockerd..."
        # 停掉我们刚才手动起的 dockerd
        local dpid
        dpid=$(cat /tmp/dockerd.pid 2>/dev/null || true)
        if [[ -n "${dpid}" ]]; then
            as_root kill -9 "$dpid" 2>/dev/null || true
            sleep 2
        fi
        as_root pkill -9 dockerd 2>/dev/null || true
        as_root pkill -9 containerd 2>/dev/null || true
        as_root pkill -9 -f "containerd-shim" 2>/dev/null || true
        sleep 2
        as_root rm -f /var/run/docker.pid /var/run/docker.sock /tmp/dockerd.pid 2>/dev/null || true
        as_root rm -rf /var/lib/docker/image /var/lib/docker/vfs /var/lib/docker/tmp /var/lib/docker/tmp-old \
                       /var/lib/docker/buildkit /var/lib/docker/containers /var/lib/docker/network 2>/dev/null || true
        log_info "storage 清理完成，将重新走 dockerd 启动流程..."
        # 返回非 0 → 让外层重新走手动启动 dockerd 流程（会重新选 driver、拉 base image，稳定）
        return 1
    fi
    log_info "vfs storage 元数据自检通过（${docker_info_sd}）"
    return 0
}
if ! ensure_vfs_storage_clean; then
    # 递归式：重来一次 ensure docker daemon（用同样的存储选择逻辑，只要不再检测到损坏就过）
    if ! (run_docker info >/dev/null 2>&1); then
        log_info "重新启动 dockerd（带干净 storage）..."
        declare -a DOCKERD_STORAGE_ARGS=()
        DOCKERD_LAUNCHED=0
        for sd in overlay2 fuse-overlayfs vfs; do
            DOCKERD_STORAGE_ARGS=(--storage-driver="$sd")
            log_info "  试 storage-driver=$sd（重新启动 clean dockerd）..."
            as_root mkdir -p /var/run /var/lib/docker /var/log
            as_root rm -f /var/run/docker.pid /var/run/docker.sock /tmp/dockerd.pid 2>/dev/null || true
            as_root pkill -9 dockerd 2>/dev/null || true
            as_root pkill -9 containerd 2>/dev/null || true
            sleep 1
            as_root /usr/bin/dockerd "${DOCKERD_STORAGE_ARGS[@]}" \
                --iptables=false --ip-masq=false --bridge=none \
                --pidfile=/tmp/dockerd.pid \
                > /tmp/dockerd-build.log 2>&1 &
            DOCKERD_PID=$!
            THIS_OK=0
            for i in $(seq 1 20); do
                sleep 1
                if [[ -S /var/run/docker.sock ]]; then
                    if (run_docker info >/dev/null 2>&1); then
                        THIS_OK=1
                        DOCKERD_LAUNCHED=1
                        log_ok "dockerd 重启成功 (storage-driver=$sd, pid=$DOCKERD_PID, clean storage)"
                        # 再跑一次一致性自检（这次肯定过）
                        ensure_vfs_storage_clean || true
                        break 2
                    fi
                fi
                if ! (as_root kill -0 "$DOCKERD_PID" 2>/dev/null); then
                    break
                fi
            done
            if [[ "$THIS_OK" != "1" ]]; then
                as_root kill -9 "$DOCKERD_PID" 2>/dev/null || true
                wait "$DOCKERD_PID" 2>/dev/null || true
            fi
        done
        if [[ "$DOCKERD_LAUNCHED" != "1" ]] && ! (run_docker info >/dev/null 2>&1); then
            log_error "clean dockerd 重启仍不可用，请查看 /tmp/dockerd-build.log"
            exit 1
        fi
    fi
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

# ---- 1.1.6) 关键：prepare_staging_dir() - 为 HAI 220G 小盘优化的构建上下文
#             vfs storage driver 每 1 个 RUN/COPY 指令 = 父层全量物理复制一次
#             因此我们做了 2 个结构性优化降低磁盘峰值占用：
#        优化 A（Dockerfile 里做）：把 8+ 个 COPY/RUN 合并成 1 COPY + 1 RUN
#                  减少 vfs 快照层数 8 → 2，省约 6×24G = 144GB 峰值占用
#        优化 B（这里做）：
#          - STAGING_DIR 放在 /tmp/.vvt-staging-XXXX（tmpfs 内存盘 + 不在 PROJECT_ROOT 里，
#            彻底避免 cp -a \".../.\" into itself 的路径嵌套经典报错）
#          - 先自动 apt install rsync（腾讯内网源 ~2 秒装好，失败退回 cp 兜底）
#          - rsync/cp 源码树 → 干净的 staging 目录，
#            排除所有运行时写入 / 缓存 / __pycache__ / *.pyc / data/output/run/sock 等
#          - 把 Dockerfile、docker-entrypoint.sh 复制进 staging
#          - docker build 上下文 = /tmp/.vvt-staging-XXXX
#          - build 前后立刻 rm -rf staging（trap + 成功后手动双保险）释放 ~20G
# ----
STAGING_DIR="/tmp/.vvt-staging-$(date +%s)"
STAGING_READY=0
cleanup_staging() {
    if [[ -n "${STAGING_DIR:-}" ]] && [[ -d "${STAGING_DIR}" ]]; then
        log_info "清理 staging 目录：${STAGING_DIR}"
        rm -rf "${STAGING_DIR}" 2>/dev/null || true
    fi
}
trap cleanup_staging EXIT INT TERM

prepare_staging_dir() {
    log_section "准备构建上下文 staging：${STAGING_DIR}（HAI 小盘优化，省 ~140G 峰值占用）"
    [[ -d "${STAGING_DIR}" ]] && rm -rf "${STAGING_DIR}" 2>/dev/null
    mkdir -p "${STAGING_DIR}"

    # 先尽量自动装好 rsync（腾讯内网 mirrors.tencentyun.com ~2 秒装好；装不上再 cp 兜底）
    if ! command -v rsync >/dev/null 2>&1; then
        log_info "宿主机未安装 rsync，尝试 apt-get install -y rsync（~2秒装好）..."
        if command -v apt-get >/dev/null 2>&1; then
            (apt-get update -y -q 2>&1 | tail -3) || true
            if apt-get install -y -q --no-install-recommends rsync 2>&1 | tail -3; then
                log_ok "rsync 已安装：$(command -v rsync)"
            else
                log_warn "apt 装 rsync 失败，退回 find | cp -a 兜底（也能用，但 staging 在 /tmp 下不会嵌套）"
            fi
        else
            log_warn "没有 apt-get，退回 cp 兜底"
        fi
    fi

    if command -v rsync >/dev/null 2>&1; then
        log_info "使用 rsync 增量同步 → staging（速度快、自动去冗余、天然无嵌套风险）"
        rsync -a --delete \
              --exclude='.git' \
              --exclude='.gitignore' \
              --exclude='.vscode' \
              --exclude='.idea' \
              --exclude='.venv' \
              --exclude='node_modules' \
              --exclude='__pycache__' \
              --exclude='*.pyc' \
              --exclude='*.pyo' \
              --exclude='*.log' \
              --exclude='*.sock' \
              --exclude='.DS_Store' \
              --exclude='frontend/.vite' \
              --exclude='frontend/dist/*-stats.json' \
              --exclude='data/logs/*' \
              --exclude='data/run/*' \
              --exclude='data/outputs/*' \
              --exclude='data/uploads/*' \
              --exclude='data/temp/*' \
              --exclude='data/stats/*' \
              --exclude='.vvt-staging*' \
              --exclude='build-v*.log' \
              --exclude='nohup.out' \
              "${PROJECT_ROOT}/" \
              "${STAGING_DIR}/" 2>&1 | tail -20 || true
    else
        log_warn "没有 rsync，使用 find + cp -a（staging 在 /tmp，不会出现 cp into itself 的嵌套报错）"
        # STAGING_DIR 在 /tmp/... 下，跟 ${PROJECT_ROOT} 完全不在一个路径里，
        # 所以 cp -a PROJECT_ROOT/... → STAGING_DIR/... 不会自我嵌套。
        # 但我们仍然用 find 主动排除 build-v*.log / nohup.out / __pycache__ 等无用文件。
        cd "${PROJECT_ROOT}"
        find . -maxdepth 1 -mindepth 1 \
             ! -name '.vvt-staging*' \
             ! -name 'build-v*.log' \
             ! -name 'nohup.out' \
             -exec cp -a {} "${STAGING_DIR}/" \; 2>/dev/null || true
        # 手动再清理无用目录
        for d in .git .vscode .idea __pycache__ .venv node_modules frontend/.vite \
                 data/logs data/run data/outputs data/uploads data/temp data/stats; do
            rm -rf "${STAGING_DIR:?}/${d}" 2>/dev/null || true
        done
        find "${STAGING_DIR}" \( -name "*.pyc" -o -name "*.pyo" -o -name "*.log" -o -name "*.sock" -o -name ".DS_Store" \) \
             -delete 2>/dev/null || true
    fi

    # 关键：把 Dockerfile 和 docker-entrypoint.sh 复制到 staging
    for need in Dockerfile docker-entrypoint.sh .env.example; do
        if [[ -f "${PROJECT_ROOT}/${need}" ]]; then
            cp -a "${PROJECT_ROOT}/${need}" "${STAGING_DIR}/${need}"
        fi
    done

    # 关键必带的大目录二次确认（rsync 误 exclude 了就白搭）：
    for must in index-tts/.venv index-tts/checkpoints frontend/node_modules frontend/dist; do
        if [[ -d "${PROJECT_ROOT}/${must}" ]]; then
            if [[ ! -d "${STAGING_DIR}/${must}" ]]; then
                log_warn "staging 缺少 ${must}，手动复制..."
                mkdir -p "${STAGING_DIR}/${must%/*}"
                cp -a "${PROJECT_ROOT}/${must}" "${STAGING_DIR}/${must}"
            fi
            sz=$(du -sh "${STAGING_DIR}/${must}" | awk '{print $1}')
            log_info "  staging 含：${must} (${sz})"
        elif [[ "$must" == "frontend/dist" ]]; then
            log_warn "宿主机 frontend/dist 不存在，Dockerfile 的兜底 RUN 会 fallback 到 5173 vite dev。可手动 npm run build 重试"
        fi
    done

    # .dockerignore 自检最后再做一次
    if [[ -f "${STAGING_DIR}/.dockerignore" ]] && grep -Eq '^\s*frontend/dist\s*$' "${STAGING_DIR}/.dockerignore"; then
        log_error "staging 中的 .dockerignore 仍有 frontend/dist 行！会把宿主机构建好的 dist 从 build context 中剔除"
        log_error "请手动删除 ${PROJECT_ROOT}/.dockerignore 里的 frontend/dist 行"
        exit 1
    fi

    STAG_SIZE=$(du -sh "${STAGING_DIR}" | awk '{print $1}')
    log_ok "staging 就绪：${STAGING_DIR} = ${STAG_SIZE}（tmpfs 内存盘，build 结束后会自动 rm 释放）"

    # ---- 关键结构性优化：在 staging 根打 payload.tar ----
    # 新 Dockerfile 不再 COPY . /app + 大 RUN（vfs 两条指令 = 两次父层全量物理拷贝 ≈ 44G 叠加峰值）
    # 新 Dockerfile：COPY payload.tar（小层，= tar 纯字节流不展开到 /app）
    #              + 1 条 RUN（tar xf payload.tar 到 /app + chmod/chown/软链/dist 校验/sanity 全部合并在同一 layer）
    # → VFS 快照层数：COPY 大项目 + RUN 大 post = 2 层 ≈ 44G 峰值
    #                    → COPY payload.tar（小层）+ RUN 解压+post（单 1 层 22G） = 约 24G 峰值
    # 省掉的一层 "22G 父 copy" 直接把 217G 盘的峰值从 133G → ≈ 95G 左右，稳稳 <80%。
    log_info "在 staging 根生成 payload.tar（Dockerfile COPY payload.tar + RUN tar xf 合并，VFS 省 1 层 22G 快照峰值）"
    PAYLOAD_TAR="${STAGING_DIR}/payload.tar"
    (
        cd "${STAGING_DIR}"
        # ⚠️ 不要加 --totals：HAI vfs + LXC 下 22G tar 读两遍 + 回传到日志管道极易 hang IO
        #     只做 tar cf（稳定、无 stdout 风暴），大小我们后面 du -sh 报
        tar \
            --exclude='./payload.tar' \
            --exclude='./Dockerfile' \
            --exclude='./docker-entrypoint.sh' \
            -cf "${PAYLOAD_TAR}" .
    )
    # payload.tar 必须存在，否则 docker build 会在 COPY payload.tar 那步直接 fail
    if [[ ! -s "${PAYLOAD_TAR}" ]]; then
        log_error "生成 payload.tar 失败（文件不存在或大小为 0）：${PAYLOAD_TAR}"
        exit 1
    fi
    TAR_SIZE=$(du -sh "${PAYLOAD_TAR}" | awk '{print $1}')
    log_ok "payload.tar 已就绪：${PAYLOAD_TAR} = ${TAR_SIZE}（与旧 COPY . /app 相同大小，但 VFS 省 1 层 22G 快照）"

    # ---- 结构性再优化：只保留 3 个文件在 staging 根，其余项目文件删掉 ----
    # 为什么：Legacy builder（无 BuildKit）在 Sending build context 时，
    # 会把整个 staging 目录先打 tar → 再解到 /var/lib/docker/tmp/docker-builder-XXXX/ 里。
    # 现在 staging 根是："项目文件 20G + payload.tar 20G = 40G"，
    # legacy builder 解出来后 docker-builder-XXXX 也有两份（20G 项目 + 20G tar），
    # 叠加 /tmp/.vvt-staging 本身 = 40G × 2 = 80G 重复占用，
    # 217G 盘直接到 216G 100%（build-v1.0.0-20260823-055908.log 就是这么爆的）。
    #
    # 修复：payload.tar 已经把所有项目文件打包了一遍，build context 其实只需要 3 个文件：
    #   (1) payload.tar            （COPY payload.tar /.vvt-payload.tar 用）
    #   (2) Dockerfile             （docker build -f 读）
    #   (3) docker-entrypoint.sh   （最后 COPY 到镜像里的启动脚本）
    # 其余 "项目文件" 全部从 staging 根删除，保证 build context 大小 ≈ 20G 单份，
    # legacy builder 再解 tar 时 docker-builder-XXXX 也只有 20G（payload.tar 单份）+ 2 个小文件，
    # 峰值少约 20G → 从 216G → ≈ 160G（217G 盘 73%），稳稳不会爆。
    log_info "瘦身 staging 根：payload.tar 已打包项目，删除多余源文件，让 build context = payload.tar 单份 ≈20G（省 20G 重复占用）"
    BEFORE=$(du -sh "${STAGING_DIR}" | awk '{print $1}')
    (
        cd "${STAGING_DIR}" || exit 1
        # find -mindepth 1 -maxdepth 1 列出 staging 根所有直接子项，
        # 保留：payload.tar、Dockerfile、docker-entrypoint.sh
        # 其余全部 rm -rf（项目文件、.venv、checkpoints、node_modules、源码、.gitignore …）
        find . -mindepth 1 -maxdepth 1 ! -name 'payload.tar' ! -name 'Dockerfile' ! -name 'docker-entrypoint.sh' -exec rm -rf {} +
    )
    AFTER=$(du -sh "${STAGING_DIR}" | awk '{print $1}')
    log_ok "staging 瘦身：${BEFORE} → ${AFTER}（后续 legacy builder docker-builder-* 只存 payload.tar 单份，不会再双份叠加）"

    # 再次断言：staging 必须有 3 个必要文件
    for must in payload.tar Dockerfile docker-entrypoint.sh; do
        if [[ ! -e "${STAGING_DIR}/${must}" ]]; then
            log_error "staging 瘦身缺必要文件：${STAGING_DIR}/${must}"
            exit 1
        fi
    done
    # 断言：staging 里不该再有项目源目录（index-tts、frontend、backend、scripts、configs…），
    # 否则瘦身失败，build context 还会爆双份
    if [[ -d "${STAGING_DIR}/index-tts" || -d "${STAGING_DIR}/frontend" || -d "${STAGING_DIR}/backend" || -d "${STAGING_DIR}/scripts" ]]; then
        log_error "staging 瘦身不彻底，仍存在源目录（会导致 legacy builder 双份叠加爆盘）"
        log_error "  存在的项目大目录："
        du -sh "${STAGING_DIR}"/index-tts "${STAGING_DIR}"/frontend "${STAGING_DIR}"/backend "${STAGING_DIR}"/scripts 2>/dev/null || true
        exit 1
    fi

    export STAGING_READY=1
}

# ---- 1.1.5) 关键：宿主机构建 frontend/dist（避免 Docker Stage 1 容器内 npm ci 崩溃导致 tsc 丢失） ----
#      宿主机有完整的 node_modules + package-lock.json，直接在这里跑更稳
#      dist/ 会被 Stage 2 的 COPY . /app 直接带进镜像，优先级高于 Stage 1 容器内 build
log_section "宿主机构建前端 frontend/dist（稳定，优先于容器内 Stage 1 build）"
DIST_READY=0
cd "${PROJECT_ROOT}/frontend"
if [ -d node_modules ] && [ -x node_modules/.bin/tsc ] && [ -x node_modules/.bin/vite ]; then
    log_info "本地 node_modules + tsc + vite 均已就绪，直接 build"
    if npm run build 2>&1 | tail -20; then
        DIST_COUNT=$(find dist -type f 2>/dev/null | wc -l)
        if [ -f dist/index.html ] && [ "$DIST_COUNT" -gt 1 ]; then
            log_ok "前端 build 成功：dist/index.html 存在（共 ${DIST_COUNT} 个文件）"
            DIST_READY=1
        else
            log_warn "npm run build 返回 0，但 dist/index.html 不合法（count=$DIST_COUNT），尝试跳过 tsc 直接 vite build..."
        fi
    else
        log_warn "宿主机构建 frontend/dist 失败（npm run build 非 0），尝试跳过 tsc 直接 vite build..."
    fi
    # 兜底：不跑 tsc，直接 vite build（vite 只做打包，不做 TS 类型检查）
    if [[ "$DIST_READY" != "1" ]]; then
        if (npx --no-install vite build 2>&1 | tail -20) && [ -f dist/index.html ]; then
            DIST_COUNT=$(find dist -type f 2>/dev/null | wc -l)
            log_ok "vite build（无 tsc）兜底成功（共 ${DIST_COUNT} 个文件）"
            DIST_READY=1
        fi
    fi
else
    log_warn "宿主机 frontend/node_modules/tsc/vite 不完整，尝试 npm ci 重装..."
    if (npm ci --no-audit --no-fund --legacy-peer-deps 2>&1 | tail -20) && npm run build 2>&1 | tail -20; then
        if [ -f dist/index.html ]; then
            log_ok "本地 npm ci + build 成功"
            DIST_READY=1
        fi
    fi
fi
cd "${PROJECT_ROOT}"
if [[ "$DIST_READY" == "1" ]]; then
    SIZE_DIST=$(du -sh "${PROJECT_ROOT}/frontend/dist" | awk '{print $1}')
    log_info "frontend/dist 就绪，大小=${SIZE_DIST}，已解除 .dockerignore 对 frontend/dist 的忽略，将通过 COPY . /app 注入镜像（8080 端口可用）"
    # 关键自检：确认 .dockerignore 真的没有再 ignore frontend/dist
    if grep -Eq '^\s*frontend/dist\s*$' "${PROJECT_ROOT}/.dockerignore"; then
        log_error ".dockerignore 仍有 frontend/dist 行！会导致 build context 丢掉 dist，必须手动删掉"
        exit 1
    fi
else
    log_warn "宿主机构建 frontend/dist 失败，Docker 构建将退回 Stage 1 容器内 build + 最后兜底到 5173 vite dev server"
fi

# ---- 1.2) 自动选构建期 apt 镜像源（解决 docker 容器内 apt DNS 失败 / 公网慢的问题） ----
#      优先级: APT_MIRROR env 覆盖 > CLI --apt-mirror > tencent-intranet(能 ping 通就用) > tencent > china > official
APT_MIRROR_AUTO="official"
if [[ -z "${APT_MIRROR:-}" ]] && command -v curl >/dev/null 2>&1; then
    if (curl -fsSL --max-time 3 http://mirrors.tencentyun.com/ubuntu/ >/dev/null 2>&1); then
        APT_MIRROR_AUTO="tencent-intranet"
    elif (curl -fsSL --max-time 5 https://mirrors.cloud.tencent.com/ubuntu/ >/dev/null 2>&1); then
        APT_MIRROR_AUTO="tencent"
    elif (curl -fsSL --max-time 5 https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ >/dev/null 2>&1); then
        APT_MIRROR_AUTO="china"
    fi
fi
BUILD_APT_MIRROR="${APT_MIRROR:-${APT_MIRROR_AUTO}}"
log_info "Docker 构建期 APT 镜像源: ${BUILD_APT_MIRROR}"

# ---- 1.3) build 日志策略：实时写 /tmp/vvt-build.log + 终端 tail -f（避免 tail -60 看起来像卡住） ----
BUILD_LOG="/tmp/vvt-build-$(date +%s).log"
: > "${BUILD_LOG}"
log_info "构建日志实时写入: ${BUILD_LOG}，终端同时实时显示（避免像卡住）"

# ---- 1.4) 准备 staging 目录（HAI 220G 小盘优化：COPY/RUN 合并到 2 层 + 上下文干净） ----
prepare_staging_dir
BUILD_CONTEXT="${STAGING_DIR}"
# Dockerfile 路径：使用项目根的 Dockerfile（staging 里也复制了一份，但 -f 指定 PROJECT_ROOT 更稳）
BUILD_DOCKERFILE="${PROJECT_ROOT}/Dockerfile"
[ -f "${STAGING_DIR}/Dockerfile" ] || cp -a "${BUILD_DOCKERFILE}" "${STAGING_DIR}/Dockerfile"
[ -f "${STAGING_DIR}/docker-entrypoint.sh" ] || cp -a "${PROJECT_ROOT}/docker-entrypoint.sh" "${STAGING_DIR}/docker-entrypoint.sh"

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

# ---- 2.1) 判断 docker 构建能力：优先 buildx → 次选 BuildKit 原生 build（--progress 可选） → 最后 legacy builder ----
BUILD_CMD="build"
BUILD_EXTRA_ARGS=()
# 0. 强制 --network=host（HAI 环境下我们手动起 dockerd 时带了 --bridge=none，无 docker bridge 网络，
#    build 容器内默认网络没有 DNS/路由，会导致 apt-get update DNS 失败 → 所有包 Unable to locate package。
#    --network=host 让 build 容器直接共享宿主机网络栈，既能解析 HAI 内网 mirrors.tencentyun.com，
#    又能走公网，是当前环境下唯一可靠的 build 联网方式。
BUILD_EXTRA_ARGS+=(--network=host)
# 1. 优先 docker buildx build（支持 --progress + 更稳的多阶段）
if (run_docker buildx version >/dev/null 2>&1); then
    BUILD_CMD="buildx build"
    BUILD_EXTRA_ARGS=(--network=host --progress=plain --load)
    log_info "检测到 docker buildx，使用 buildx build（--network=host，更稳的多阶段构建）"
else
    # 2. 没有 buildx 就看 legacy build --help 里有没有 --progress（有的话可以开 plain）
    if (run_docker build --help 2>/dev/null | grep -qw -- '--progress'); then
        BUILD_EXTRA_ARGS=(--network=host --progress=plain)
        log_info "docker build 原生支持 --progress，使用 plain 模式 + --network=host"
    else
        log_warn "当前 docker.io 是 legacy builder（无 --progress），跳过 BuildKit 特有参数，使用普通 docker build + --network=host"
        BUILD_EXTRA_ARGS=(--network=host)
        # legacy builder 不认 DOCKER_BUILDKIT=1 的 --progress，但普通 build 一样能走多阶段 FROM=frontend-build
        unset DOCKER_BUILDKIT
        unset BUILDKIT_PROGRESS
    fi
fi

run_docker ${BUILD_CMD} \
    --file "${BUILD_DOCKERFILE}" \
    --tag "${TMP_TAG}" \
    --build-arg "BUILD_VERSION=${VERSION}" \
    --build-arg "APT_MIRROR=${BUILD_APT_MIRROR}" \
    "${BUILD_EXTRA_ARGS[@]}" \
    "${BUILD_CONTEXT}" 2>&1 | tee -a "${BUILD_LOG}" | tail -n +1

BUILD_RC=${PIPESTATUS[0]}
if [[ "${BUILD_RC}" != "0" ]]; then
    log_error "Docker build 失败（返回码 ${BUILD_RC}）。完整日志见 ${BUILD_LOG}，最后 60 行："
    tail -60 "${BUILD_LOG}"
    # build 失败但 staging 可能占用 ~20G，手动释放（EXIT trap 也会触发）
    cleanup_staging || true
    log_warn "也可以跳过 build 直接跳过镜像部署（hai-deploy.sh 有源码 install.sh 兜底，用户端 10~20 分钟出页）。"
    exit 1
fi

log_ok "本地镜像构建完成: ${TMP_TAG}"

# build 成功后立即释放 staging（~20-25GB 立刻回到磁盘可用空间）
# 防止后面 docker push 阶段 staging 还占着 20G 导致磁盘余量紧张
cleanup_staging || true
log_info "staging 目录已释放（BUILD_CONTEXT），可用空间增加约 20-25GB"

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
