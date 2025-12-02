#!/bin/bash
# 仅启动前端

# 使用Cursor IDE的Node.js版本
NODE_PATH="/root/.cursor-server/bin/60d42bed27e5775c43ec0428d8c653c49e58e260/node"

if [ ! -x "$NODE_PATH" ]; then
    echo "❌ 找不到Node.js: $NODE_PATH"
    echo "请检查Cursor IDE是否正确安装"
    exit 1
fi

cd "$(dirname "$0")/frontend"
# 使用 --host 0.0.0.0 允许外部访问
echo "🚀 启动前端服务..."
"$NODE_PATH" ./node_modules/.bin/vite --host 0.0.0.0 --port 5173

