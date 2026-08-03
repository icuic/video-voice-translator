#!/bin/bash
# 一键安装脚本 - 自动完成所有安装步骤

set -e

# 获取脚本所在目录的绝对路径（脚本在项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
cd "${PROJECT_ROOT}"

echo "=========================================="
echo "🚀 一键安装脚本"
echo "=========================================="
echo "将自动完成所有安装步骤，包括："
echo "  - 系统依赖（FFmpeg、lsof、Node.js、Python 3.11）"
echo "  - IndexTTS2 安装（包含模型文件下载，约 5.5GB）"
echo "  - AMD/ROCm PyTorch 安装与校验"
echo "  - IndexTTS2 运行时 HuggingFace 缓存预热"
echo "  - 主项目依赖安装"
echo "  - 前端依赖安装"
echo "  - 翻译 LLM 配置（.env）"
echo "=========================================="
echo ""

# 检查是否为 root 用户
if [ "$EUID" -eq 0 ]; then
    SUDO_CMD=""
else
    SUDO_CMD="sudo"
fi

# 步骤1: 安装系统依赖
echo "=========================================="
echo "📦 步骤 1/8: 安装系统依赖"
echo "=========================================="

# 检查并安装 Python 3.11（推荐用于 IndexTTS2 环境）
if ! command -v python3.11 &> /dev/null; then
    echo "安装 Python 3.11..."
    $SUDO_CMD apt-get update
    $SUDO_CMD apt-get install -y python3.11 python3.11-venv python3.11-dev
    echo "✅ Python 3.11 安装完成: $(python3.11 --version)"
else
    echo "✅ Python 3.11 已安装: $(python3.11 --version)"
fi

# 检查 FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "安装 FFmpeg..."
    $SUDO_CMD apt-get update
    $SUDO_CMD apt-get install -y ffmpeg
    echo "✅ FFmpeg 安装完成"
else
    echo "✅ FFmpeg 已安装: $(ffmpeg -version | head -1)"
fi

# 检查 lsof
if ! command -v lsof &> /dev/null; then
    echo "安装 lsof..."
    $SUDO_CMD apt-get install -y lsof
    echo "✅ lsof 安装完成"
else
    echo "✅ lsof 已安装"
fi

# 检查并安装 Node.js
if ! command -v node &> /dev/null; then
    echo "安装 Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | $SUDO_CMD bash -
    $SUDO_CMD apt-get install -y nodejs
    echo "✅ Node.js 安装完成: $(node --version)"
else
    echo "✅ Node.js 已安装: $(node --version)"
fi

# 步骤2: 安装 IndexTTS2
echo ""
echo "=========================================="
echo "📦 步骤 2/8: 安装 IndexTTS2"
echo "=========================================="

if [ ! -f "${PROJECT_ROOT}/scripts/install/install_index_tts.sh" ]; then
    echo "❌ 找不到 install_index_tts.sh 脚本"
    exit 1
fi

export UV_PYTHON="${UV_PYTHON:-python3.11}"

bash "${PROJECT_ROOT}/scripts/install/install_index_tts.sh"

# 步骤3: 安装/修复 ROCm PyTorch（AMD）
echo ""
echo "=========================================="
echo "🧩 步骤 3/8: 安装/修复 ROCm PyTorch"
echo "=========================================="

HAS_ROCM=false
if [ "${FORCE_ROCM:-}" = "1" ]; then
    HAS_ROCM=true
elif [ -d "/opt/rocm" ]; then
    HAS_ROCM=true
elif command -v rocminfo >/dev/null 2>&1; then
    HAS_ROCM=true
fi

if [ "${HAS_ROCM}" = "true" ]; then
    if [ ! -f "${PROJECT_ROOT}/scripts/install/install_rocm_pytorch.sh" ]; then
        echo "❌ 找不到 install_rocm_pytorch.sh 脚本"
        exit 1
    fi
    bash "${PROJECT_ROOT}/scripts/install/install_rocm_pytorch.sh"
else
    echo "⚠️  未检测到 ROCm 环境，跳过 ROCm PyTorch 安装（如需强制安装，设置 FORCE_ROCM=1）"
fi

# 步骤4: 预热 IndexTTS2 运行时 HuggingFace 缓存
echo ""
echo "=========================================="
echo "📥 步骤 4/8: 预热 IndexTTS2 运行时 HuggingFace 缓存"
echo "=========================================="

if [ "${SKIP_HF_PREWARM:-}" = "1" ]; then
    echo "已跳过预热（SKIP_HF_PREWARM=1）"
else
    if [ -x "${PROJECT_ROOT}/index-tts/.venv/bin/python" ]; then
        export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
        export HF_HOME="${PROJECT_ROOT}/index-tts/.cache/hf"
        "${PROJECT_ROOT}/index-tts/.venv/bin/python" "${PROJECT_ROOT}/scripts/install/prewarm_indextts_hf_cache.py" || {
            echo "⚠️  预热失败（可能是网络受限）。可后续再执行："
            echo "   HF_ENDPOINT=https://hf-mirror.com ${PROJECT_ROOT}/index-tts/.venv/bin/python ${PROJECT_ROOT}/scripts/install/prewarm_indextts_hf_cache.py"
        }
    else
        echo "⚠️  未找到 index-tts 虚拟环境，跳过预热"
    fi
fi

# 步骤5: 安装主项目依赖
echo ""
echo "=========================================="
echo "📦 步骤 5/8: 安装主项目依赖"
echo "=========================================="

if [ ! -f "${PROJECT_ROOT}/scripts/install/install_with_uv_china.sh" ]; then
    echo "❌ 找不到 install_with_uv_china.sh 脚本"
    exit 1
fi

bash "${PROJECT_ROOT}/scripts/install/install_with_uv_china.sh"

# 步骤6: 安装前端依赖
echo ""
echo "=========================================="
echo "📦 步骤 6/8: 安装前端依赖"
echo "=========================================="

if ! command -v npm &> /dev/null; then
    echo "❌ 错误: npm 未找到，但 Node.js 应该已安装"
    echo "   请检查 Node.js 安装是否正确"
    exit 1
fi

cd "${PROJECT_ROOT}/frontend"
if [ ! -d "node_modules" ]; then
    echo "安装前端依赖..."
    npm install
    echo "✅ 前端依赖安装完成"
else
    echo "✅ 前端依赖已安装"
fi
cd "${PROJECT_ROOT}"

# 最终验证
echo ""
echo "=========================================="
echo "🔍 最终验证"
echo "=========================================="

cd "${PROJECT_ROOT}/index-tts"
source .venv/bin/activate
cd "${PROJECT_ROOT}"

# 验证依赖
if python tools/check_dependencies.py 2>/dev/null; then
    echo "✅ 所有依赖验证通过"
else
    echo "⚠️  部分依赖验证失败，请检查"
fi

# 验证 IndexTTS2
if python -c "from indextts.infer_v2 import IndexTTS2; print('✅ IndexTTS2 可以正常导入')" 2>/dev/null; then
    echo "✅ IndexTTS2 可以正常导入"
else
    echo "⚠️  IndexTTS2 导入失败（可能是模型文件未下载）"
fi

# 验证模型文件
if [ -f "${PROJECT_ROOT}/index-tts/checkpoints/gpt.pth" ] && [ -f "${PROJECT_ROOT}/index-tts/checkpoints/s2mel.pth" ]; then
    echo "✅ 模型文件已下载"
else
    echo "⚠️  模型文件未找到，音色克隆功能将无法使用"
fi

# 步骤7: 配置翻译 LLM（.env）
echo ""
echo "=========================================="
echo "⚙️  步骤 7/8: 配置翻译 LLM（.env）"
echo "=========================================="

ENV_FILE="${PROJECT_ROOT}/.env"
if [ ! -f "${ENV_FILE}" ]; then
    if [ -f "${PROJECT_ROOT}/.env.example" ]; then
        cp "${PROJECT_ROOT}/.env.example" "${ENV_FILE}"
        echo "✅ 已生成 ${ENV_FILE}（请填写 LLM_API_KEY 后重启服务）"
    else
        echo "⚠️  未找到 .env.example，请手动创建 ${ENV_FILE}"
    fi
fi

# 步骤8: 安装完成提示
echo ""
echo "=========================================="
echo "🎉 安装完成！"
echo "=========================================="
echo ""
echo "下一步可以："
echo "1. 启动 Gradio Web UI（推荐新手）: ./run_webui.sh"
echo "   访问: http://localhost:7861"
echo ""
echo "2. 启动前后端分离模式: ./service.sh up"
echo "   前端: http://localhost:5173"
echo "   后端 API: http://localhost:8000"
echo "   API 文档: http://localhost:8000/docs"
echo ""
echo "3. 使用 supervisor（推荐云上，SSH断线不影响）: ./supervisor.sh up"
echo ""
echo "4. 使用命令行: ./run_cli.sh input.mp4"
echo ""
echo "如果遇到问题，请查看："
echo "- 安装文档: docs/INSTALL.md"
echo "- 使用指南: docs/USAGE.md"
echo "- IndexTTS2 官方文档: https://github.com/index-tts/index-tts"
echo ""
