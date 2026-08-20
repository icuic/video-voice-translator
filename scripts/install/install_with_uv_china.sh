#!/bin/bash
# 使用 uv 安装主项目额外依赖（国内镜像版）
# 说明: 本脚本「默认」用国内镜像, 但如果父进程已经通过环境变量指定了
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

# 1. HTTP 超时 (父脚本 install_all.sh 已经 export 过, 这里给个默认值)
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-120}"

# 2. PyPI 默认镜像: 环境变量优先, 否则用阿里云
CHINA_PYPI="https://mirrors.aliyun.com/pypi/simple"
if [[ -z "${UV_DEFAULT_INDEX}" ]]; then
    export UV_DEFAULT_INDEX="${CHINA_PYPI}"
fi

echo "=========================================="
echo "📦 使用 uv 安装主项目额外依赖（国内镜像）"
echo "=========================================="
echo "UV_HTTP_TIMEOUT=${UV_HTTP_TIMEOUT}s"
echo "PyPI index:      ${UV_DEFAULT_INDEX}"
echo ""

cd index-tts

echo "安装主项目额外依赖..."
# uv pip install 会自动读 UV_DEFAULT_INDEX / UV_HTTP_TIMEOUT 环境变量,
# 这里再显式加一次 --index-url 是为了兼容老版本 uv.
uv pip install -r ../requirements_project.txt --index-url "${UV_DEFAULT_INDEX}"

cd ..

echo ""
echo "验证安装..."
cd index-tts
source .venv/bin/activate
cd ..

if [ -f "${PROJECT_ROOT}/config.yaml" ]; then
    WHISPER_BACKEND=$(grep -A 1 "^whisper:" "${PROJECT_ROOT}/config.yaml" | grep "backend:" | awk '{print $2}' | tr -d '"' || echo "faster-whisper")
else
    WHISPER_BACKEND="faster-whisper"
fi

VERIFY_CMD="import scipy; import httpx; import pydub; import openai; import resemblyzer; import ninja; "
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
