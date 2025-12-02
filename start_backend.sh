#!/bin/bash
# 仅启动后端（使用虚拟环境）

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

# 检查虚拟环境是否存在
if [ ! -d "${INDEX_TTS_DIR}/.venv" ]; then
    echo "❌ 虚拟环境不存在，请先安装 index-tts 依赖"
    echo "   运行: cd index-tts && uv sync --extra webui"
    exit 1
fi

# 激活虚拟环境
cd "${INDEX_TTS_DIR}"
source .venv/bin/activate

# 设置环境变量（参考 run_webui.sh）
if [ -f ~/.bashrc ]; then
    DASHSCOPE_KEY=$(grep "^export DASHSCOPE_API_KEY=" ~/.bashrc | head -1 | cut -d'"' -f2)
    if [ -n "$DASHSCOPE_KEY" ]; then
        export DASHSCOPE_API_KEY="$DASHSCOPE_KEY"
    fi
    HF_ENDPOINT_VAL=$(grep "^export HF_ENDPOINT=" ~/.bashrc | head -1 | cut -d'"' -f2)
    if [ -n "$HF_ENDPOINT_VAL" ]; then
        export HF_ENDPOINT="$HF_ENDPOINT_VAL"
    fi
fi

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HOME="${INDEX_TTS_DIR}/.cache/hf"
export PYTHONUNBUFFERED=1
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

# CUDA/CuDNN 运行时库路径
export LD_LIBRARY_PATH="${INDEX_TTS_DIR}/.venv/lib/python3.10/site-packages/nvidia/cudnn/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"
export PATH="/usr/local/cuda/bin:${PATH}"

# 返回项目目录
cd "${PROJECT_ROOT}"

# 使用虚拟环境中的 Python 启动后端
echo "🚀 启动后端服务（使用虚拟环境）..."
"${INDEX_TTS_DIR}/.venv/bin/python" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload --limit-max-requests 1000 --timeout-keep-alive 300
