#!/bin/bash
# 按照 index-tts 官方建议使用国内源安装主项目依赖

set -e

# 获取脚本所在目录的绝对路径，然后回到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

echo "=========================================="
echo "📦 使用 uv 安装主项目额外依赖"
echo "按照 index-tts 官方建议使用国内镜像源"
echo "=========================================="
echo ""

# 进入 index-tts 目录
cd index-tts

# 按照 index-tts README.md 中的建议使用国内镜像源
# 官方文档建议使用：--default-index "https://mirrors.aliyun.com/pypi/simple"
# 或：--default-index "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"

echo "使用阿里云镜像源安装依赖（按照 index-tts 官方建议）..."
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
    echo "✅ IndexTTS 依赖: 已安装"
    echo "✅ 主项目额外依赖: 已安装（使用国内源）"
    echo ""
    echo "下一步可以："
    echo "1. 启动 Web UI: ./run_webui.sh"
    echo "2. 使用命令行: ./run_cli.sh input.mp4 --source-lang en --target-lang zh"
else
    echo "⚠️  部分依赖可能未正确安装，请检查"
    exit 1
fi
