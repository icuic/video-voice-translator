#!/bin/bash
# 仅启动前端

# 检查系统安装的 Node.js
if ! command -v node &> /dev/null; then
    echo "❌ 错误: 找不到 Node.js"
    echo "请先运行安装脚本安装 Node.js: ./install_all.sh"
    echo "或手动安装: curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs"
    exit 1
fi

NODE_CMD="node"

cd "$(dirname "$0")/frontend"
# 使用 --host 0.0.0.0 允许外部访问
echo "🚀 启动前端服务..."
"$NODE_CMD" ./node_modules/.bin/vite --host 0.0.0.0 --port 5173

