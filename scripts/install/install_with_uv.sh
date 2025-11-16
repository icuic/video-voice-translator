#!/bin/bash
# 使用 uv 安装主项目额外依赖（推荐方式）

set -e

# 获取脚本所在目录的绝对路径，然后回到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

echo "=========================================="
echo "📦 使用 uv 安装主项目额外依赖"
echo "=========================================="
echo "优势：更快、更可靠、与 index-tts 管理方式一致"
echo ""

# 进入 index-tts 目录（uv 需要知道虚拟环境位置）
cd index-tts

# 使用 uv pip install 在现有虚拟环境中安装依赖
# uv pip install 会自动使用当前项目的虚拟环境
echo "使用 uv pip install 安装依赖..."
uv pip install -r ../requirements_project.txt

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
