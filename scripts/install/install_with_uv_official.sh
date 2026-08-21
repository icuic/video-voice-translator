#!/bin/bash
# 使用 uv 安装主项目额外依赖（官方源版）
# 说明: 本脚本「默认」用 PyPI 官方源, 但如果父进程已经通过环境变量指定了
#       UV_DEFAULT_INDEX / UV_HTTP_TIMEOUT, 则以环境变量为准。

set -e
set -o pipefail

if ! command -v uv &>/dev/null && [ -x "$HOME/.local/bin/uv" ]; then
    export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v uv &>/dev/null; then
    echo "📦 安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

# 1. HTTP 超时 (父脚本 install.sh 已经 export 过, 这里给个默认值)
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-120}"

# 2. PyPI 默认镜像: 环境变量优先, 否则用官方
OFFICIAL_PYPI="https://pypi.org/simple"
if [[ -z "${UV_DEFAULT_INDEX}" ]]; then
    export UV_DEFAULT_INDEX="${OFFICIAL_PYPI}"
fi

echo "=========================================="
echo "📦 使用 uv 安装主项目额外依赖（官方源）"
echo "=========================================="
echo "UV_HTTP_TIMEOUT=${UV_HTTP_TIMEOUT}s"
echo "PyPI index:      ${UV_DEFAULT_INDEX}"
echo ""

cd index-tts

echo "安装主项目额外依赖..."
uv pip install -r ../requirements_project.txt --index-url "${UV_DEFAULT_INDEX}"

cd ..

echo ""
echo "验证安装..."
cd index-tts
source .venv/bin/activate
cd ..

if python -c "import whisper; import scipy; import httpx; import pydub; print('✅ 所有依赖验证通过')" 2>&1; then
    echo ""
    echo "=========================================="
    echo "🎉 安装完成！"
    echo "=========================================="
    echo ""
    echo "✅ IndexTTS 依赖: 已安装"
    echo "✅ 主项目额外依赖: 已安装（使用官方源）"
    echo ""
    echo "下一步可以："
    echo "1. 启动前后端分离服务（推荐）: ./manage-supervisor.sh start"
    echo "   查看服务状态              : ./manage-supervisor.sh status"
    echo "2. 使用命令行: ./run_cli.sh input.mp4 --source-lang en --target-lang zh"
else
    echo "⚠️  部分依赖可能未正确安装，请检查"
    exit 1
fi
