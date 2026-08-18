#!/bin/bash
# 按照 index-tts 官方 README.md 安装步骤

set -e

# 获取脚本所在目录的绝对路径，然后回到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=========================================="
echo "IndexTTS 安装脚本（按照官方文档）"
echo "=========================================="

# 步骤0: 检查并安装 uv
if ! command -v uv &> /dev/null; then
    echo "📦 检测到 uv 未安装，正在安装..."
    pip install -U uv
    echo "✅ uv 安装完成"
else
    echo "✅ uv 已安装: $(uv --version 2>/dev/null | head -1 || echo '已安装')"
fi

# 步骤1: 克隆 IndexTTS2 仓库（如果不存在或为空）
if [ ! -d "${PROJECT_ROOT}/index-tts" ] || [ ! -f "${PROJECT_ROOT}/index-tts/pyproject.toml" ]; then
    if [ -d "${PROJECT_ROOT}/index-tts" ] && [ ! -f "${PROJECT_ROOT}/index-tts/pyproject.toml" ]; then
        echo ""
        echo "⚠️  检测到 index-tts 目录存在但为空或不完整，正在重新克隆..."
        rm -rf "${PROJECT_ROOT}/index-tts"
    else
        echo ""
        echo "📥 检测到 index-tts 目录不存在，正在克隆仓库..."
    fi
    git clone https://github.com/index-tts/index-tts.git "${PROJECT_ROOT}/index-tts"
    echo "✅ IndexTTS2 仓库克隆完成"
else
    echo "✅ IndexTTS2 仓库已存在"
fi

cd "${PROJECT_ROOT}/index-tts"

# 切换到指定的 commit（确保版本一致性）
INDEX_TTS_PINNED_COMMIT="c7d3cff0ff8402c1d8e94b9848305d47e39f981c"
echo ""
echo "🔒 切换 IndexTTS2 到指定 commit: ${INDEX_TTS_PINNED_COMMIT}"
git checkout "${INDEX_TTS_PINNED_COMMIT}"
echo "✅ IndexTTS2 已切换到 commit: $(git rev-parse --short HEAD)"

# 验证 pyproject.toml 是否存在
if [ ! -f "pyproject.toml" ]; then
    echo "❌ 错误: 在 index-tts 目录中找不到 pyproject.toml 文件"
    echo "   请检查仓库是否正确克隆"
    exit 1
fi

# 步骤2: 检查并安装 git-lfs（用于下载示例音频文件）
if ! command -v git-lfs &> /dev/null; then
    echo "📦 检测到 git-lfs 未安装，正在安装..."
    # 检查是否为 root 用户
    if [ "$EUID" -eq 0 ]; then
        SUDO_CMD=""
    else
        SUDO_CMD="sudo"
    fi
    $SUDO_CMD apt-get update
    $SUDO_CMD apt-get install -y git-lfs
    echo "✅ git-lfs 安装完成"
else
    echo "✅ git-lfs 已安装"
fi

# 启用 Git-LFS 并下载示例音频文件（按照官方文档）
echo "配置 Git-LFS..."
git lfs install
echo "下载示例音频文件..."
git lfs pull
echo "✅ 示例音频文件下载完成"

# 步骤3: 使用 uv 安装依赖（使用国内镜像加速）
echo ""
echo "📦 开始安装依赖（使用阿里云镜像）..."
echo "   这可能需要几分钟时间，请耐心等待..."

# 使用 --all-extras 安装所有功能（包括 webui）
uv sync --all-extras --default-index "https://mirrors.aliyun.com/pypi/simple"

echo ""
echo "✅ IndexTTS 依赖安装完成！"

# 步骤4: 验证安装
echo ""
echo "🔍 验证 IndexTTS2 安装..."
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    if python -c "from indextts.infer_v2 import IndexTTS2; print('✅ IndexTTS2 安装成功')" 2>/dev/null; then
        echo "✅ IndexTTS2 安装验证通过"
    else
        echo "⚠️  IndexTTS2 导入验证失败，但依赖已安装"
        echo "   这可能是正常的，模型文件下载后即可使用"
    fi
    deactivate
else
    echo "⚠️  虚拟环境未找到，跳过验证"
fi

# 步骤5: 下载模型文件（必需）
echo ""
echo "=========================================="
echo "📥 步骤 5: 下载 IndexTTS2 模型文件（必需）"
echo "=========================================="
echo "⚠️  模型文件较大（约 5.5GB），下载可能需要一些时间"
echo ""

if [ ! -f ".venv/bin/activate" ]; then
    echo "❌ 虚拟环境不存在，无法下载模型"
    exit 1
fi

source .venv/bin/activate

# 检查模型是否已下载
if [ -f "checkpoints/gpt.pth" ] && [ -f "checkpoints/s2mel.pth" ]; then
    echo "✅ 模型文件已存在，跳过下载"
    MODEL_SIZE=$(du -sh checkpoints/ 2>/dev/null | awk '{print $1}' || echo "未知")
    echo "   模型目录大小: ${MODEL_SIZE}"
else
    echo "开始下载模型文件..."
    
    # 配置 HF_ENDPOINT（用于模型下载和运行时）
    if ! grep -q "HF_ENDPOINT" ~/.bashrc 2>/dev/null; then
        echo "配置 HF_ENDPOINT（国内镜像，用于加速模型下载）..."
        echo 'export HF_ENDPOINT="https://hf-mirror.com"' >> ~/.bashrc
        export HF_ENDPOINT="https://hf-mirror.com"
        echo "✅ HF_ENDPOINT 已配置到 ~/.bashrc"
    else
        # 从 ~/.bashrc 读取已配置的值
        export HF_ENDPOINT=$(grep "^export HF_ENDPOINT=" ~/.bashrc | head -1 | cut -d'"' -f2)
        echo "✅ 使用已配置的 HF_ENDPOINT: ${HF_ENDPOINT}"
    fi
    
    DOWNLOAD_FAILED=false
    
    # 优先使用 ModelScope（国内用户）
    echo "尝试使用 ModelScope 下载模型（国内推荐）..."
    if ! command -v modelscope &> /dev/null; then
        echo "安装 modelscope..."
        uv tool install modelscope || {
            echo "⚠️  modelscope 安装失败，尝试使用 HuggingFace..."
            DOWNLOAD_FAILED=true
        }
    fi
    
    if [ "$DOWNLOAD_FAILED" = "false" ] && command -v modelscope &> /dev/null; then
        if modelscope download --model IndexTeam/IndexTTS-2 --local_dir checkpoints 2>&1; then
            echo "✅ 使用 ModelScope 下载成功"
        else
            echo "⚠️  ModelScope 下载失败，尝试使用 HuggingFace..."
            DOWNLOAD_FAILED=true
        fi
    fi
    
    # 如果 ModelScope 失败或不可用，使用 HuggingFace
    if [ "$DOWNLOAD_FAILED" = "true" ] || [ ! -f "checkpoints/gpt.pth" ]; then
        echo "使用 HuggingFace 下载模型..."
        if ! command -v hf &> /dev/null; then
            echo "安装 huggingface-hub..."
            uv tool install "huggingface-hub[cli,hf_xet]" || {
                echo "❌ huggingface-hub 安装失败"
                exit 1
            }
        fi
        hf download IndexTeam/IndexTTS-2 --local-dir=checkpoints || {
            echo "❌ HuggingFace 下载失败"
            exit 1
        }
    fi
    
    # 验证模型文件
    if [ -f "checkpoints/gpt.pth" ] && [ -f "checkpoints/s2mel.pth" ]; then
        MODEL_SIZE=$(du -sh checkpoints/ 2>/dev/null | awk '{print $1}' || echo "未知")
        echo "✅ 模型文件下载完成！模型目录大小: ${MODEL_SIZE}"
    else
        echo "❌ 模型文件下载失败，请手动下载"
        echo "   参考文档: https://github.com/index-tts/index-tts"
        exit 1
    fi
fi

deactivate
cd "${PROJECT_ROOT}"

echo ""
echo "=========================================="
echo "✅ IndexTTS2 安装完成！"
echo "=========================================="
echo ""
echo "下一步：安装主项目额外依赖"
echo "   ./scripts/install/install_with_uv_china.sh"
echo ""
