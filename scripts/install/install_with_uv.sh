#!/bin/bash
# 使用 uv 安装主项目额外依赖（通用版本: 不强制镜像，以环境变量 UV_DEFAULT_INDEX 为准）
# 说明:
#   UV_HTTP_TIMEOUT (默认 120s)       uv 请求超时
#   UV_DEFAULT_INDEX (默认 PyPI 官方)  不建议配置; 需要国内镜像请用 install_with_uv_china.sh

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

export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-120}"

echo "=========================================="
echo "📦 使用 uv 安装主项目额外依赖"
echo "=========================================="
echo "UV_HTTP_TIMEOUT=${UV_HTTP_TIMEOUT}s"
if [[ -n "${UV_DEFAULT_INDEX}" ]]; then
    echo "PyPI index (环境变量): ${UV_DEFAULT_INDEX}"
    PIP_INDEX_ARGS="--index-url ${UV_DEFAULT_INDEX}"
else
    echo "PyPI index: default"
    PIP_INDEX_ARGS=""
fi
echo "优势：更快、更可靠、与 index-tts 管理方式一致"
echo ""

cd index-tts

echo "使用 uv pip install 安装依赖..."
# shellcheck disable=SC2086
uv pip install -r ../requirements_project.txt ${PIP_INDEX_ARGS}

cd ..

echo ""
echo "验证安装..."
cd index-tts
source .venv/bin/activate
cd ..

# 读取配置文件确定使用的 Whisper 后端
if [ -f "${PROJECT_ROOT}/config.yaml" ]; then
    WHISPER_BACKEND=$(grep -A 1 "^whisper:" "${PROJECT_ROOT}/config.yaml" | grep "backend:" | awk '{print $2}' | tr -d '"' || echo "faster-whisper")
else
    WHISPER_BACKEND="faster-whisper"
fi

# 根据配置检查对应的后端
VERIFY_CMD="import scipy; import httpx; import pydub; import openai; import resemblyzer; import ninja; import demucs; "
if [ "$WHISPER_BACKEND" = "faster-whisper" ] || [ "$WHISPER_BACKEND" = "" ]; then
    VERIFY_CMD="${VERIFY_CMD}import faster_whisper; "
    BACKEND_NAME="faster-whisper"
else
    VERIFY_CMD="${VERIFY_CMD}import whisper; "
    BACKEND_NAME="openai-whisper"
fi
VERIFY_CMD="${VERIFY_CMD}print('✅ 所有依赖验证通过（使用 ${BACKEND_NAME} 后端）')"

if python -c "${VERIFY_CMD}" 2>&1; then
    echo ""
    echo "=========================================="
    echo "🎉 安装完成！"
    echo "=========================================="
    echo ""
    echo "下一步可以："
    echo "1. 启动前后端分离服务（推荐）: ./manage-supervisor.sh start"
    echo "   查看服务状态              : ./manage-supervisor.sh status"
    echo "2. 使用命令行: ./run_cli.sh input.mp4"
else
    echo "⚠️  部分依赖可能未正确安装，请检查"
    echo "   当前配置使用后端: ${BACKEND_NAME}"
    exit 1
fi
