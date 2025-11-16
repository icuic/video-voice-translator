#!/bin/bash
# 使用 uv 安装主项目额外依赖（使用国内镜像源）

set -e

# 获取脚本所在目录的绝对路径，然后回到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

echo "=========================================="
echo "📦 使用 uv 安装主项目额外依赖（国内镜像）"
echo "=========================================="
echo "使用阿里云镜像源加速下载"
echo ""

# 进入 index-tts 目录
cd index-tts

# 使用 uv pip install 并指定国内镜像源
# 方法1: 使用环境变量
export UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple"

echo "使用阿里云镜像源安装依赖..."
uv pip install -r ../requirements_project.txt --index-url https://mirrors.aliyun.com/pypi/simple

cd ..

echo ""
echo "验证安装..."
cd index-tts
source .venv/bin/activate
cd ..

if python -c "import gradio; import whisper; import scipy; import httpx; import pydub; print('✅ 所有依赖验证通过')" 2>&1; then
    echo ""
    echo "=========================================="
    echo "🎉 安装完成！"
    echo "=========================================="
    echo ""
    echo "下一步可以："
    echo "1. 启动 Web UI: ./run_webui.sh"
    echo "2. 使用命令行: ./run_cli.sh input.mp4"
else
    echo "⚠️  部分依赖可能未正确安装，请检查"
    exit 1
fi
