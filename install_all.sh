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
echo "  - 系统依赖（FFmpeg、lsof）"
echo "  - IndexTTS2 安装（包含模型文件下载，约 5.5GB）"
echo "  - 主项目依赖安装"
echo "  - 环境变量配置"
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
echo "📦 步骤 1/6: 安装系统依赖"
echo "=========================================="

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

# 步骤2: 安装 IndexTTS2
echo ""
echo "=========================================="
echo "📦 步骤 2/6: 安装 IndexTTS2"
echo "=========================================="

if [ ! -f "${PROJECT_ROOT}/scripts/install/install_index_tts.sh" ]; then
    echo "❌ 找不到 install_index_tts.sh 脚本"
    exit 1
fi

bash "${PROJECT_ROOT}/scripts/install/install_index_tts.sh"

# 步骤3: 检查 PyTorch
echo ""
echo "=========================================="
echo "🔍 步骤 3/6: 检查 PyTorch"
echo "=========================================="

if [ -f "${PROJECT_ROOT}/index-tts/.venv/bin/activate" ]; then
    cd "${PROJECT_ROOT}/index-tts"
    source .venv/bin/activate
    
    if python -c "import torch; print(f'✅ PyTorch 已安装: {torch.__version__}'); print(f'   CUDA 可用: {torch.cuda.is_available()}')" 2>/dev/null; then
        python -c "import torch; print(f'✅ PyTorch 已安装: {torch.__version__}'); print(f'   CUDA 可用: {torch.cuda.is_available()}')"
    else
        echo "⚠️  PyTorch 未安装或无法导入"
        echo "   这可能是正常的，IndexTTS2 依赖安装时会自动安装 PyTorch"
    fi
    
    cd "${PROJECT_ROOT}"
else
    echo "⚠️  虚拟环境不存在，跳过 PyTorch 检查"
fi

# 步骤4: 安装主项目依赖
echo ""
echo "=========================================="
echo "📦 步骤 4/6: 安装主项目依赖"
echo "=========================================="

if [ ! -f "${PROJECT_ROOT}/scripts/install/install_with_uv_china.sh" ]; then
    echo "❌ 找不到 install_with_uv_china.sh 脚本"
    exit 1
fi

bash "${PROJECT_ROOT}/scripts/install/install_with_uv_china.sh"

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

# 步骤6: 配置环境变量
echo ""
echo "=========================================="
echo "⚙️  步骤 6/6: 配置环境变量"
echo "=========================================="

# 注意：HF_ENDPOINT 已在 install_index_tts.sh 中配置（模型下载时）
echo "✅ HF_ENDPOINT 已在 IndexTTS2 安装时配置"

# 配置 DASHSCOPE_API_KEY
if ! grep -q "DASHSCOPE_API_KEY" ~/.bashrc 2>/dev/null; then
    echo ""
    echo "⚠️  DASHSCOPE_API_KEY 未配置"
    echo "   翻译功能需要此配置"
    echo ""
    
    # 检查是否在交互式终端中
    if [ -t 0 ]; then
        echo "请输入您的 DASHSCOPE_API_KEY（留空跳过，稍后手动配置）："
        read -r DASHSCOPE_API_KEY
        
        if [ -n "$DASHSCOPE_API_KEY" ]; then
            echo "export DASHSCOPE_API_KEY='${DASHSCOPE_API_KEY}'" >> ~/.bashrc
            echo "✅ DASHSCOPE_API_KEY 已配置到 ~/.bashrc"
            echo "   请运行 'source ~/.bashrc' 或重新打开终端使配置生效"
        else
            echo "⚠️  已跳过配置，请稍后手动在 ~/.bashrc 中添加："
            echo "   export DASHSCOPE_API_KEY='your-api-key-here'"
        fi
    else
        # 非交互式环境，只显示提示
        echo "   请在 ~/.bashrc 中添加："
        echo "   export DASHSCOPE_API_KEY='your-api-key-here'"
        echo ""
        echo "   或者设置环境变量后重新运行此脚本："
        echo "   export DASHSCOPE_API_KEY='your-api-key-here'"
        echo "   ./scripts/install/install_all.sh"
    fi
else
    echo "✅ DASHSCOPE_API_KEY 已配置"
fi

echo ""
echo "=========================================="
echo "🎉 安装完成！"
echo "=========================================="
echo ""
echo "下一步可以："
echo "1. 启动 Web UI: ./run_webui.sh"
echo "2. 使用命令行: ./run_cli.sh input.mp4"
echo ""
echo "如果遇到问题，请查看："
echo "- 安装文档: docs/INSTALL.md"
echo "- IndexTTS2 官方文档: https://github.com/index-tts/index-tts"
echo ""

