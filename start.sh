#!/bin/bash
# 一键启动脚本 - 同时启动后端和前端

set -e

# 获取脚本所在目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Video Voice Translator 一键启动${NC}"
echo -e "${BLUE}========================================${NC}"

# 检查后端依赖
echo -e "${YELLOW}检查后端依赖...${NC}"
cd "$SCRIPT_DIR/backend"
if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo -e "${YELLOW}安装后端依赖...${NC}"
    pip3 install -q -r requirements.txt
fi

# 统一加载 nvm（如果存在），确保使用 Node.js 20
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use 20 2>/dev/null || true

# 检查前端依赖
echo -e "${YELLOW}检查前端依赖...${NC}"
cd "$SCRIPT_DIR/frontend"
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}安装前端依赖...${NC}"
    npm install
fi

# 清理函数
cleanup() {
    echo -e "\n${YELLOW}正在停止服务...${NC}"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# 启动后端（使用虚拟环境）
echo -e "${GREEN}启动后端服务 (端口 8000，监听所有接口，使用虚拟环境)...${NC}"

# 检查虚拟环境
INDEX_TTS_DIR="$SCRIPT_DIR/index-tts"
if [ ! -d "$INDEX_TTS_DIR/.venv" ]; then
    echo -e "${YELLOW}❌ 错误: 虚拟环境不存在${NC}"
    echo -e "${YELLOW}请先运行: cd index-tts && uv sync --extra webui${NC}"
    exit 1
fi

# 使用虚拟环境启动后端
cd "$INDEX_TTS_DIR"
source .venv/bin/activate

# 设置环境变量（参考 start_backend.sh）
# 优先使用已存在的环境变量，否则从 ~/.bashrc 读取
if [ -z "$DASHSCOPE_API_KEY" ] && [ -f ~/.bashrc ]; then
    # 支持单引号和双引号两种格式
    DASHSCOPE_LINE=$(grep "^export DASHSCOPE_API_KEY=" ~/.bashrc | head -1)
    if [ -n "$DASHSCOPE_LINE" ]; then
        # 尝试提取单引号或双引号中的值
        DASHSCOPE_KEY=$(echo "$DASHSCOPE_LINE" | sed -n "s/.*['\"]\(.*\)['\"].*/\1/p")
        if [ -n "$DASHSCOPE_KEY" ]; then
            export DASHSCOPE_API_KEY="$DASHSCOPE_KEY"
        fi
    fi
fi

if [ -z "$HF_ENDPOINT" ] && [ -f ~/.bashrc ]; then
    HF_ENDPOINT_LINE=$(grep "^export HF_ENDPOINT=" ~/.bashrc | head -1)
    if [ -n "$HF_ENDPOINT_LINE" ]; then
        HF_ENDPOINT_VAL=$(echo "$HF_ENDPOINT_LINE" | sed -n "s/.*['\"]\(.*\)['\"].*/\1/p")
        if [ -n "$HF_ENDPOINT_VAL" ]; then
            export HF_ENDPOINT="$HF_ENDPOINT_VAL"
        fi
    fi
fi

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HOME="$INDEX_TTS_DIR/.cache/hf"
export PYTHONUNBUFFERED=1
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

# CUDA/CuDNN 运行时库路径
export LD_LIBRARY_PATH="${INDEX_TTS_DIR}/.venv/lib/python3.10/site-packages/nvidia/cudnn/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"
export PATH="/usr/local/cuda/bin:${PATH}"

cd "$SCRIPT_DIR"
"${INDEX_TTS_DIR}/.venv/bin/python" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload --limit-max-requests 1000 --timeout-keep-alive 300 --limit-concurrency 1000 --backlog 2048 > /tmp/backend.log 2>&1 &
BACKEND_PID=$!

# 等待后端启动
sleep 2

# 检查后端是否启动成功
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${YELLOW}后端启动中，请稍候...${NC}"
    sleep 3
fi

# 启动前端（监听所有接口，允许外部访问）
echo -e "${GREEN}启动前端服务 (端口 5173，监听所有接口)...${NC}"

# 检查 Node.js 是否可用
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}❌ 错误: 找不到 Node.js${NC}"
    echo -e "${YELLOW}请先运行安装脚本安装 Node.js: ./install_all.sh${NC}"
    echo -e "${YELLOW}或手动安装: curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs${NC}"
    exit 1
fi

cd "$SCRIPT_DIR/frontend"
node ./node_modules/.bin/vite --host 0.0.0.0 --port 5173 > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!

# 等待前端启动
sleep 3

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ 服务已启动！${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${BLUE}前端地址: ${NC}http://localhost:5173"
echo -e "${BLUE}后端 API: ${NC}http://localhost:8000"
echo -e "${BLUE}API 文档: ${NC}http://localhost:8000/docs"
echo -e "${GREEN}========================================${NC}"
echo -e "${YELLOW}按 Ctrl+C 停止所有服务${NC}"
echo ""

# 显示日志（可选）
if [ "$1" == "--logs" ]; then
    echo -e "${YELLOW}显示日志（按 Ctrl+C 停止）...${NC}"
    tail -f /tmp/backend.log /tmp/frontend.log
else
    # 等待用户中断
    wait
fi
