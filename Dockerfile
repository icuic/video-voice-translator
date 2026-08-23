# ============================================================
# AI 音视频翻译系统 - Dockerfile
# 预打包全部模型（IndexTTS2）+ 虚拟环境 + 前端 build 产物
# 让新用户从 hai-deploy.sh 的 docker 路径 3~8 分钟启动完毕
#
# 设计目标：
#   1) HAI vfs storage driver（无 CoW，每层=父层全量物理复制）下
#      镜像层数量尽可能少（RUN/COPY 指令越少越好）
#      避免 24GB × 10 层 = 240GB 把 220G 盘撑爆
#      -> 下面把项目文件 COPY + 所有 post-install RUN 合并成
#         【1 COPY + 1 RUN】（总共 2 个新层 + apt 层 + 2×ENTRYPOINT 小层 = 约 5 层）
#   2) 前端构建全部搬到宿主机（scripts/build_push_images.sh 执行）
#      容器内不再执行任何 npm install / build，避免 HAI + vfs 下
#      npm Exit handler never called / 网络失败
#   3) 使用 runtime 版 nvidia/cuda（~3GB）而非 devel 版（~8GB）
# ============================================================

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS runtime

# ---- 构建期参数：宿主机 build_push_images.sh 传入，决定容器内 apt 源 ----
ARG APT_MIRROR=auto

ENV DEBIAN_FRONTEND=noninteractive

# ---- ① 基础系统依赖（APT 层，第 1 个大层） ----
# 包含 rsync：给 build_push_images.sh 的 prepare_staging_dir() 在宿主机用
# 这里的 rsync 也给容器内未来同步挂载卷用
RUN set -eux; \
    case "${APT_MIRROR}" in \
        tencent-intranet) \
            sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.tencentyun.com/ubuntu/|g' /etc/apt/sources.list; \
            sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.tencentyun.com/ubuntu/|g' /etc/apt/sources.list; \
            rm -f /etc/apt/sources.list.d/*.list 2>/dev/null || true; \
            ;; \
        tencent) \
            sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.cloud.tencent.com/ubuntu/|g' /etc/apt/sources.list; \
            sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.cloud.tencent.com/ubuntu/|g' /etc/apt/sources.list; \
            rm -f /etc/apt/sources.list.d/*.list 2>/dev/null || true; \
            ;; \
        china) \
            sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' /etc/apt/sources.list; \
            sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' /etc/apt/sources.list; \
            rm -f /etc/apt/sources.list.d/*.list 2>/dev/null || true; \
            ;; \
        *) \
            rm -f /etc/apt/sources.list.d/*.list 2>/dev/null || true; \
            ;; \
    esac; \
    for i in 1 2 3; do \
        if apt-get update -y -q; then break; fi; \
        echo "[apt] update round $i failed, retry in 10s" >&2; sleep 10; \
    done; \
    apt-get install -y -q --no-install-recommends \
        ca-certificates curl wget unzip ffmpeg rsync supervisor \
        python3 python3-venv python3-pip \
        git tzdata locales bash-completion gosu \
        libsndfile1 libgomp1 libsox-dev sox; \
    rm -rf /var/lib/apt/lists/*; \
    locale-gen en_US.UTF-8 zh_CN.UTF-8 2>/dev/null || true; \
    ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime; \
    echo "Asia/Shanghai" > /etc/timezone; \
    groupadd -r -g 999 vvt; \
    useradd -r -u 999 -g vvt -s /bin/bash -d /app vvt; \
    gosu nobody true

ENV LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8 \
    TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ENV APP_ROOT=/app \
    INDEX_TTS_DIR=/app/index-tts \
    PROJECT_ROOT=/app

WORKDIR /app

# ---- ② payload.tar 模式：把「项目文件 COPY」+「合并 post-install」
#      合成单 1 个 RUN，VFS 下只产 1 次全量 24GB 父拷贝，
#      替代旧 COPY . /app + RUN 两条（会产 2 次 24GB，217G 小盘峰值超爆）
#
# payload.tar 由 scripts/build_push_images.sh prepare_staging_dir 在 build context
# 目录（/tmp/.vvt-staging-*）里 tar 出来，放在 build context 根下，
# 所以 docker build 时 build context 里就一个 payload.tar + Dockerfile +
# docker-entrypoint.sh（约 22GB，和旧 COPY 一样大小，但层数少了 1 层大的）。
COPY payload.tar /tmp/.vvt-payload.tar

# ---- ③ 合并：tar 解压 payload.tar 到 /app + 所有 post-install（chmod/chown/权限/
#        预置目录/dist 校验/python软链/node软链/预置.env/sanity/BUILD_VERSION）
#        —— 第 2 个（也是最后 1 个）大层；VFS 全父拷贝只发生这一次 ----
# 为什么合并：vfs 每 1 个 RUN/COPY = 1 次父层全量物理复制
#   旧 8 个 RUN/COPY = 24 * 8 = 192GB 峰值，217G 盘 100%
#   新 2 个大层（apt + payload/post）+ 2 条 entrypoint 小层 = 约 4 层
RUN set -eux; \
    # (0) 先 tar xf payload.tar 进 /app（替代旧 COPY . /app）
    #     tar 会保留权限+owner，但我们后面 chown -R vvt:vvt，所以先 root 解压没问题
    mkdir -p /app; \
    tar --totals -xf /tmp/.vvt-payload.tar -C /app; \
    rm -f /tmp/.vvt-payload.tar; \
    # (A) 脚本可执行
    for s in hai-deploy.sh configure.sh update_project.sh install.sh manage-supervisor.sh; do \
        [ -x "/app/$s" ] || chmod +x "/app/$s" 2>/dev/null || true; \
    done; \
    find /app/scripts -type f -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true; \
    \
    # (B) 给 PyTorch / index-tts 用的 python 软链（与宿主机 install.sh 行为一致）
    VENV_PY="/app/index-tts/.venv/bin/python"; \
    if [ -x "${VENV_PY}" ] && [ ! -e /usr/local/bin/python ]; then \
        ln -sf "${VENV_PY}" /usr/local/bin/python; \
    fi; \
    if [ -x "${VENV_PY}" ] && [ ! -e /usr/local/bin/activate-tts ]; then \
        ln -sf /app/index-tts/.venv/bin/activate /usr/local/bin/activate-tts 2>/dev/null || true; \
    fi; \
    \
    # (C) 前端 vite/node 软链：让 docker-entrypoint.sh 的 vite preview / vite dev 能全局找到 vite
    FRONTEND_VITE="/app/frontend/node_modules/.bin/vite"; \
    FRONTEND_NODE_MODS="/app/frontend/node_modules"; \
    if [ -d "${FRONTEND_NODE_MODS}/.bin" ]; then \
        export PATH="${FRONTEND_NODE_MODS}/.bin:${PATH}"; \
        for bin_node in vite tsc node npm npx; do \
            if [ -x "${FRONTEND_NODE_MODS}/.bin/${bin_node}" ]; then \
                [ -e "/usr/local/bin/${bin_node}" ] || ln -sf "${FRONTEND_NODE_MODS}/.bin/${bin_node}" "/usr/local/bin/${bin_node}" 2>/dev/null || true; \
            fi; \
        done; \
    fi; \
    [ -x "${FRONTEND_VITE}" ] || true; \
    \
    # (D) supervisor / 运行时 空目录：保证容器首次启（无挂载卷）时也能写
    mkdir -p /app/data/logs/supervisor \
             /app/data/run \
             /app/data/uploads \
             /app/data/outputs \
             /app/data/temp \
             /app/data/stats \
             /app/env \
             /app/tmp; \
    \
    # (E) 预置空 .env（如果未提供；运行时挂载 /env-mount/.env 会覆盖）
    if [ ! -f /app/.env ] && [ -f /app/.env.example ]; then \
        gosu vvt cp /app/.env.example /app/.env; \
    fi; \
    \
    # (F) 权限：APP_ROOT 下除 data/env 挂载点专属目录以外，其余 vvt:vvt 可读
    #     注意：用户侧 docker-compose.yml 会把 /app/data /app/env 挂载成卷，
    #     所以这里即使 chown 也会被覆盖，但容器首次 run（没挂载卷）时要有权限写
    chown -R vvt:vvt /app; \
    chmod 755 /app /app/index-tts /app/frontend /app/backend /app/scripts 2>/dev/null || true; \
    \
    # (G) 前端 dist 合法性最终校验（唯一来源：宿主机 npm run build 产物 tar 进镜像）
    #     合法：index.html 存在 + 文件数 > 1（Vite 正常 3 个文件）
    #     不合法：清除残留占位，docker-entrypoint.sh 会 fallback 到 5173 vite dev server
    HOST_DIST="/app/frontend/dist"; \
    if [ -f "${HOST_DIST}/index.html" ] && [ "$(find "${HOST_DIST}" -type f | wc -l)" -gt 1 ]; then \
        DIST_N="$(find "${HOST_DIST}" -type f | wc -l)"; \
        echo "[frontend dist] use HOST-built dist (${HOST_DIST}/index.html OK, ${DIST_N} files)"; \
        echo "[frontend dist] port 8080 will be served by vite preview"; \
    else \
        echo "[frontend dist] WARNING: missing or invalid host-built dist"; \
        echo "[frontend dist] runtime will fallback to vite dev server on port 5173"; \
        rm -rf "${HOST_DIST}"; \
    fi; \
    echo "[frontend dist] final check:"; \
    if [ -f /app/frontend/dist/index.html ]; then \
        echo "  dist/index.html exists -> OK (port 8080 will be served)"; \
    else \
        echo "  dist/index.html NOT found -> runtime fallback to 5173 (or re-run scripts/build_push_images.sh)"; \
    fi; \
    \
    # (H) 构建版本标记：镜像里写入 BUILD_VERSION.txt，用户进容器 `cat /app/BUILD_VERSION.txt` 就能看版本
    BUILD_VERSION_ARG="${BUILD_VERSION:-unknown}"; \
    echo "BUILD_VERSION=${BUILD_VERSION_ARG}"  > /app/BUILD_VERSION.txt; \
    echo "BUILD_TIME=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> /app/BUILD_VERSION.txt; \
    echo "APT_MIRROR=${APT_MIRROR:-auto}"        >> /app/BUILD_VERSION.txt; \
    chown vvt:vvt /app/BUILD_VERSION.txt 2>/dev/null || true; \
    \
    # (I) 最后：快速 sanity check（python / vite / supervisord 真的存在 + 可执行）
    command -v python >/dev/null 2>&1 || (ls /app/index-tts/.venv/bin/python && echo "venv python exists (will be used by supervisord programs via bash -c source /app/index-tts/.venv/bin/activate)"); \
    command -v supervisord >/dev/null; \
    if [ -x "${FRONTEND_VITE}" ]; then "${FRONTEND_VITE}" --version >/dev/null 2>&1; fi; \
    true

# ---- ④ 健康检查 ----
HEALTHCHECK --interval=60s --timeout=15s --start-period=90s --retries=3 \
    CMD curl -fsSL http://127.0.0.1:8000/health >/dev/null 2>&1 || exit 1

# ---- ⑤ 入口：supervisord（backend 8000 + vite preview(dev) on 8080/5173） ----
ENV ENV_PROJECT_ROOT=/app \
    PROJECT_ROOT=/app \
    INDEX_TTS_DIR=/app/index-tts \
    DEV_MODE=0 \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000 \
    FRONTEND_HOST=0.0.0.0 \
    FRONTEND_PORT=8080

EXPOSE 8080 5173 8000

COPY docker-entrypoint.sh /usr/local/bin/vvt-entrypoint.sh
RUN set -eux; \
    chmod +x /usr/local/bin/vvt-entrypoint.sh; \
    command -v vvt-entrypoint.sh >/dev/null

ENTRYPOINT ["/usr/local/bin/vvt-entrypoint.sh"]
CMD ["supervisord"]
