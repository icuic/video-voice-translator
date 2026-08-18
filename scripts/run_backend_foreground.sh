#!/bin/bash
# 后端服务前台启动脚本（专供 supervisord 调用，也可手动前台运行）
# - 前台运行（不 detach）
# - 日志输出到 stdout/stderr，让 supervisord 接管
# - 不使用 --reload（生产模式），如需热重载请用 DEV_MODE=1

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

# 加载公共环境
source "${PROJECT_ROOT}/scripts/setup_env.sh"

# 检查虚拟环境
if [ ! -d "${INDEX_TTS_DIR}/.venv" ]; then
    echo "[supervisord:backend] ERROR: 虚拟环境不存在，请先安装 index-tts 依赖" >&2
    echo "   cd index-tts && uv sync" >&2
    exit 1
fi

# 进入项目根目录
cd "${PROJECT_ROOT}"

# 监听地址和端口（可通过环境变量覆盖）
HOST="${BACKEND_HOST:-0.0.0.0}"
PORT="${BACKEND_PORT:-8000}"

# 是否为开发模式（默认生产模式不开 reload）
if [ "$DEV_MODE" = "1" ]; then
    RELOAD_FLAG="--reload"
    echo "[supervisord:backend] 启动后端（开发模式，已开启 reload）: ${HOST}:${PORT}"
else
    RELOAD_FLAG=""
    echo "[supervisord:backend] 启动后端（生产模式）: ${HOST}:${PORT}"
fi

# 使用虚拟环境中的 Python 执行 uvicorn（前台运行，不要加 &）
exec "${INDEX_TTS_DIR}/.venv/bin/python" -m uvicorn backend.app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    $RELOAD_FLAG \
    --limit-max-requests 1000 \
    --timeout-keep-alive 300 \
    --limit-concurrency 1000 \
    --backlog 2048
