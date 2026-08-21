# ============================================================
# AI 音视频翻译系统 - Dockerfile
# 预打包全部模型（IndexTTS2）+ 虚拟环境 + 前端 build 产物
# 让新用户从 hai-deploy.sh 的 docker 路径 3~8 分钟启动完毕
#
# 基础镜像说明：
#   nvidia/cuda 系列基础镜像自带 CUDA + cuDNN，兼容 PyTorch 2.x
#   用 runtime 版（~3GB）而非 devel 版（~8GB）控体积
#   选择与 PyTorch 2.x 官方推荐一致的 CUDA 12.1
#
# 构建作者（非项目用户）专用：
#   请通过 scripts/build_push_images.sh 构建，不要直接 docker build
# ============================================================

# ---- Stage 1: 前端 build（仅在作者本机构建时需要，用户端直接 COPY 产物） ----
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /app-src
COPY frontend /app-src/frontend
WORKDIR /app-src/frontend
# 使用 npm ci（要求 package-lock.json 存在），如果失败则 fallback 到 npm install
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund 2>&1 | tail -5; \
    else npm install --no-audit --no-fund 2>&1 | tail -5; fi
RUN npm run build 2>&1 | tail -10

# ---- Stage 2: 最终运行镜像 ----
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS runtime

# ---- 基础系统依赖（最小化安装以控制镜像体积） ----
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y -q \
 && apt-get install -y -q --no-install-recommends \
        ca-certificates curl wget unzip ffmpeg rsync supervisor \
        python3 python3-venv python3-pip \
        sudo git tzdata locales bash-completion \
        libsndfile1 libgomp1 libsox-dev sox \
 && rm -rf /var/lib/apt/lists/* \
 && locale-gen en_US.UTF-8 zh_CN.UTF-8 2>/dev/null || true \
 && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
 && echo "Asia/Shanghai" > /etc/timezone

ENV LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8 \
    TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---- 镜像内固定目录结构 ----
ENV APP_ROOT=/app \
    INDEX_TTS_DIR=/app/index-tts \
    PROJECT_ROOT=/app

WORKDIR /app

# ---- 1) 复制项目代码（不含 index-tts/.venv checkpoints 等大文件，在 .dockerignore 中排除后分别 COPY） ----
COPY . /app

# ---- 2) 复制预打包的大文件（这些文件在作者本机 build 时直接注入到镜像，不再现场下载） ----
#      用 2 段 COPY 保证即使层失效也能复用大文件层
COPY index-tts/.venv /app/index-tts/.venv
COPY index-tts/checkpoints /app/index-tts/checkpoints

# ---- 3) 复制前端 build 产物（如果存在，优先用 build 好的静态文件） ----
#      如果作者没跑 Stage 1，就会用 frontend/ 自带的 node_modules 运行 vite
COPY --from=frontend-build --chown=root:root /app-src/frontend/dist /app/frontend/dist

# ---- 4) 前端 node_modules（vite 依赖） ----
COPY frontend/node_modules /app/frontend/node_modules

# ---- 5) 保证脚本可执行 ----
RUN chmod +x /app/hai-deploy.sh /app/configure.sh /app/update_project.sh \
    /app/install.sh /app/manage-supervisor.sh 2>/dev/null; \
    find /app/scripts -type f -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true

# ---- 6) 预置空 .env（如果未提供；运行时会用挂载卷覆盖） ----
RUN if [ ! -f /app/.env ] && [ -f /app/.env.example ]; then \
        cp /app/.env.example /app/.env; \
    fi

# ---- 7) 给 supervisor 在镜像里有个默认 PID 目录 ----
RUN mkdir -p /app/data/logs/supervisor /app/data/run /app/data/uploads /app/data/outputs /app/data/temp /app/data/stats

# ---- 8) 健康检查 ----
HEALTHCHECK --interval=60s --timeout=15s --start-period=90s --retries=3 \
    CMD curl -fsSL http://127.0.0.1:8000/health >/dev/null 2>&1 || exit 1

# ---- 9) 容器入口：镜像内自启 supervisord（后端 8000 + 前端 vite preview） ----
#    入口脚本会：
#      - 如果宿主机给了 /env-mount/.env，就替换 /app/.env（保持 Key 不丢）
#      - 启动 supervisord 管 backend + frontend
ENV ENV_PROJECT_ROOT=/app \
    PROJECT_ROOT=/app \
    INDEX_TTS_DIR=/app/index-tts \
    DEV_MODE=0 \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000 \
    FRONTEND_HOST=0.0.0.0 \
    FRONTEND_PORT=5173

EXPOSE 5173 8000

COPY docker-entrypoint.sh /usr/local/bin/vvt-entrypoint.sh
RUN chmod +x /usr/local/bin/vvt-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/vvt-entrypoint.sh"]
CMD ["supervisord"]
