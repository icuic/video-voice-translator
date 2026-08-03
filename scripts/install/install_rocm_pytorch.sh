#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

if [ ! -x "${INDEX_TTS_DIR}/.venv/bin/python" ]; then
    echo "❌ 未找到 index-tts 虚拟环境: ${INDEX_TTS_DIR}/.venv"
    exit 1
fi

PIP="${INDEX_TTS_DIR}/.venv/bin/pip"
PY="${INDEX_TTS_DIR}/.venv/bin/python"

TORCH_BASE_VERSION="${TORCH_BASE_VERSION:-2.8.0}"
TORCH_ROCM_VARIANTS=(
    "${TORCH_BASE_VERSION}+rocm7.2:https://download.pytorch.org/whl/rocm7.2"
    "${TORCH_BASE_VERSION}+rocm7.1:https://download.pytorch.org/whl/rocm7.1"
    "${TORCH_BASE_VERSION}+rocm6.4:https://download.pytorch.org/whl/rocm6.4"
)

echo "=========================================="
echo "🧩 安装 ROCm PyTorch（AMD）"
echo "=========================================="

"${PIP}" install -q "setuptools<81"

INSTALL_OK=false
for item in "${TORCH_ROCM_VARIANTS[@]}"; do
    VERSION="${item%%:*}"
    INDEX_URL="${item#*:}"

    echo "尝试安装 torch==${VERSION} (index-url=${INDEX_URL})..."
    if "${PIP}" install -U --index-url "${INDEX_URL}" --trusted-host download.pytorch.org \
        "torch==${VERSION}" "torchaudio==${VERSION}" ; then
        INSTALL_OK=true
        break
    fi
done

if [ "${INSTALL_OK}" != "true" ]; then
    echo "❌ ROCm PyTorch 安装失败"
    exit 1
fi

echo ""
echo "验证 PyTorch..."
"${PY}" - <<'PY'
import torch
kind = "AMD ROCm" if getattr(torch.version, "hip", None) else ("NVIDIA CUDA" if getattr(torch.version, "cuda", None) else "CPU")
print(f"✅ PyTorch: {torch.__version__}")
print(f"   GPU 可用: {torch.cuda.is_available()}")
print(f"   后端: {kind}")
PY
