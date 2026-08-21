#!/bin/bash
# ============================================================
# Docker 容器入口脚本（镜像内置 /usr/local/bin/vvt-entrypoint.sh）
# 运行用户策略：
#   1) 启动阶段（ENTRYPOINT PID 1）必须是 root：才能处理挂载卷（/app/data、/app/env）的权限归属
#      （宿主机 docker run 时新建的卷默认归属 root:root 755）
#   2) 权限修复完成后，用 gosu 切到 UID/GID=999 的非特权 vvt 用户启动 supervisord
#      Web/后端/翻译推理全在 vvt 用户下跑，永远不能碰 root 权限
# 负责：
#   1) 检测宿主机挂载的 /env-mount/.env → 替换 /app/.env（保证重启不丢 Key）
#   2) 检测 /data-mount/ 目录内容 → 软链到 /app/data/（保证翻译历史不丢）
#   3) supervisorctl 或直接前台启动 supervisord
#   4) 兼容用户参数 --help / bash / shell
# ============================================================

set -euo pipefail

log_info()  { echo -e "\033[36m[VVT-Entry]\033[0m $*"; }
log_warn()  { echo -e "\033[33m[VVT-Entry]\033[0m $*" >&2; }
log_ok()    { echo -e "\033[32m[VVT-Entry]\033[0m $*"; }

# ---- 只允许 root 跑 entrypoint（才有权限修卷），不是 root 就 warning 继续 ----
RUN_AS_ROOT=0
if [[ "$(id -u)" -eq 0 ]]; then
    RUN_AS_ROOT=1
    if ! command -v gosu >/dev/null 2>&1; then
        log_warn "镜像缺少 gosu，无法切换非特权用户，继续用 root 运行（不推荐）"
        RUN_AS_ROOT=2
    fi
fi

# 兼容用户直接 `docker run ... bash` 进容器调试
if [[ "$#" -gt 0 && "$1" != "supervisord" ]]; then
    log_info "非默认启动，直接 exec 命令: $*"
    if [[ "$RUN_AS_ROOT" == "1" && ( "$1" == "bash" || "$1" == "sh" || "$1" == "/bin/bash" || "$1" == "/bin/sh" ) ]]; then
        # 调试 shell 默认也给 vvt 用户（用户要 root 就自己 `docker exec -u root -it vvt bash`）
        exec gosu vvt "$@"
    else
        exec "$@"
    fi
fi

log_info "初始化 Docker 容器...（entrypoint 以 UID=$(id -u) 运行，结束后会 gosu 切到 vvt）"

# --------------------------------------------------------
# A. /app/.env 卷同步：宿主机挂载了 /app/env 目录，则以宿主机为准
# --------------------------------------------------------
HOST_ENV_DIR="${HOST_ENV_DIR:-/app/env}"
HOST_DATA_DIR="${HOST_DATA_DIR:-/app/data}"

mkdir -p "${HOST_ENV_DIR}" "${HOST_DATA_DIR}"

if [[ -f "${HOST_ENV_DIR}/.env" ]]; then
    log_info "检测到宿主机卷 ${HOST_ENV_DIR}/.env，同步到 /app/.env"
    cp -f "${HOST_ENV_DIR}/.env" /app/.env
else
    log_info "宿主机未提供 .env，使用镜像内默认空模板（首次启动会自动生成）"
    if [[ ! -f /app/.env && -f /app/.env.example ]]; then
        cp -f /app/.env.example /app/.env
    fi
fi
# 保证后续 Web 写入的 .env 也能持久化到宿主机卷
ln -sf /app/.env "${HOST_ENV_DIR}/.env" 2>/dev/null || true
# 让 configure.sh 写入的内容也同步到宿主机
if ! grep -q "VVT_ENV_SYNC" "${HOST_ENV_DIR}/.env.link" 2>/dev/null; then
    ln -sf /app/.env "${HOST_ENV_DIR}/.env.latest" 2>/dev/null || true
fi

# --------------------------------------------------------
# B. data 目录同步 + 挂载卷权限修复（关键！）
#    用户第一次 `docker run` 时，docker 会自动创建空卷目录，归属 root:root
#    但我们 supervisord 在 vvt 用户下跑，无权写 /app/data/uploads
# --------------------------------------------------------
for d in logs run uploads outputs temp stats demo; do
    if [[ -d "/app/data/${d}" || ! -e "/app/data/${d}" ]]; then
        mkdir -p "${HOST_DATA_DIR}/${d}" "/app/data/${d}"
        # 如果宿主机卷里已有内容就不重写（避免第一次丢失数据）
        if [[ -z "$(ls -A /app/data/${d} 2>/dev/null)" ]]; then
            cp -rn "${HOST_DATA_DIR}/${d}/." "/app/data/${d}/" 2>/dev/null || true
        fi
        # 反向 cp 新内容到卷
        cp -rn "/app/data/${d}/." "${HOST_DATA_DIR}/${d}/" 2>/dev/null || true
    fi
done

# 关键点：把两个挂载卷整个递归 chown 到 vvt，才能让非特权用户写 .env 和上传文件
if [[ "$RUN_AS_ROOT" == "1" ]]; then
    chown -R vvt:vvt /app /app/data /app/env "${HOST_DATA_DIR}" "${HOST_ENV_DIR}" 2>/dev/null || true
    log_ok "挂载卷归属已切到 vvt（UID=999）"
fi

# --------------------------------------------------------
# C. 如果前端已有 dist 产物，优先走 vite preview 静态服务器(8080)
#    否则走 vite dev(5173)，保持与 install.sh 内脚本一致
# --------------------------------------------------------
if [[ -d /app/frontend/dist && -f /app/frontend/dist/index.html ]]; then
    export FRONTEND_PORT="${FRONTEND_PORT:-8080}"
    log_info "检测到前端 dist，使用 vite preview 静态服务器 (port=${FRONTEND_PORT})"
    # 覆盖前端前台脚本命令，让 supervisord 中的前端程序自动走 preview
    cat > /tmp/vvt-frontend-preview.sh <<'PREVIEW_EOF'
#!/bin/bash
set -e
cd /app/frontend
HOST="${FRONTEND_HOST:-0.0.0.0}"
PORT="${FRONTEND_PORT:-8080}"
echo "[VVT-Docker:frontend] vite preview ${HOST}:${PORT}"
exec node ./node_modules/.bin/vite preview --host "$HOST" --port "$PORT"
PREVIEW_EOF
    chmod +x /tmp/vvt-frontend-preview.sh
    ln -sf /tmp/vvt-frontend-preview.sh /app/scripts/run_frontend_foreground.sh 2>/dev/null || true
    export FRONTEND_FOREGROUND_SCRIPT=/tmp/vvt-frontend-preview.sh
else
    export FRONTEND_PORT="${FRONTEND_PORT:-5173}"
    log_info "前端 dist 未就绪，使用 vite dev server (port=${FRONTEND_PORT})"
fi

log_ok "容器初始化完成，启动 supervisord..."
log_info "前端地址: http://<宿主机IP>:${FRONTEND_PORT}   后端 API: http://<宿主机IP>:8000/docs"
log_info "注意：supervisord 及所有子进程(FastAPI/Vite/Whisper/XTTS) 已用 gosu 以 vvt 用户运行"

if [[ "$RUN_AS_ROOT" == "1" ]]; then
    # 最稳的做法：supervisord 由 vvt 跑，不允许 supervisord 有 root
    exec gosu vvt /usr/bin/supervisord -c /app/supervisor/supervisord.conf -n
else
    # 如果 entrypoint 已经被降权（RUN_AS_ROOT=0 或缺 gosu）就直接前台跑
    exec /usr/bin/supervisord -c /app/supervisor/supervisord.conf -n
fi
