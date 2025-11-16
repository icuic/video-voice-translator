#!/bin/bash
# 按照 index-tts 官方 README.md 安装步骤

set -e

# 获取脚本所在目录的绝对路径，然后回到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=========================================="
echo "IndexTTS 安装脚本（按照官方文档）"
echo "=========================================="

cd "${PROJECT_ROOT}/index-tts"

# 步骤1: 检查 git-lfs（可选，用于下载大文件）
if ! command -v git-lfs &> /dev/null; then
    echo "⚠️  git-lfs 未安装，跳过大文件下载步骤"
    echo "   如需下载模型文件，请先安装: apt-get install git-lfs"
else
    echo "✅ git-lfs 已安装"
    git lfs install
    git lfs pull
fi

# 步骤2: 使用 uv 安装依赖（使用国内镜像加速）
echo ""
echo "📦 开始安装依赖（使用阿里云镜像）..."
echo "   这可能需要几分钟时间，请耐心等待..."

# 使用 --all-extras 安装所有功能（包括 webui）
uv sync --all-extras --default-index "https://mirrors.aliyun.com/pypi/simple"

echo ""
echo "✅ IndexTTS 依赖安装完成！"
echo ""
echo "下一步："
echo "1. 激活虚拟环境: source index-tts/.venv/bin/activate"
echo "2. 安装主项目额外依赖: ./scripts/install/install_with_uv.sh"
echo "3. 下载模型文件（可选）:"
echo "   uv tool install 'huggingface-hub[cli,hf_xet]'"
echo "   hf download IndexTeam/IndexTTS-2 --local-dir=checkpoints"
