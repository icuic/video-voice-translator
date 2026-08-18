#!/bin/bash
# 前端服务前台启动脚本（专供 supervisord 调用，也可手动前台运行）
# - 前台运行（不 detach）
# - 日志输出到 stdout/stderr，让 supervisord 接管
# - 使用 vite dev server（如需生产模式请先 npm run build，再用静态文件服务器）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"

# 统一加载 nvm（如果存在），确保使用 Node.js 20
export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
    \. "$NVM_DIR/nvm.sh"
    nvm use 20 >/dev/null 2>&1 || true
fi

# 检查 Node.js
if ! command -v node >/dev/null 2>&1; then
    echo "[supervisord:frontend] ERROR: 找不到 Node.js" >&2
    echo "   请先安装 Node.js v20+: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash - && sudo apt-get install -y nodejs" >&2
    exit 1
fi

# 检查 frontend 目录
if [ ! -d "$FRONTEND_DIR" ]; then
    echo "[supervisord:frontend] ERROR: frontend 目录不存在: $FRONTEND_DIR" >&2
    exit 1
fi

# 检查 node_modules（首次启动自动安装）
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ] || [ ! -f "node_modules/.bin/vite" ]; then
    echo "[supervisord:frontend] node_modules 不存在，正在安装前端依赖..."
    npm install || {
        echo "[supervisord:frontend] ERROR: npm install 失败" >&2
        exit 1
    }
fi

# 监听地址和端口（可通过环境变量覆盖）
HOST="${FRONTEND_HOST:-0.0.0.0}"
PORT="${FRONTEND_PORT:-5173}"

echo "[supervisord:frontend] 启动前端: ${HOST}:${PORT}"

# 前台执行 vite（vite 本身就是前台运行，不用加 &）
exec node ./node_modules/.bin/vite \
    --host "$HOST" \
    --port "$PORT"
