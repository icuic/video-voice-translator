#!/bin/bash

# 音视频翻译 Web UI 启动脚本

echo "🎬 启动音视频翻译 Web UI..."

# 获取脚本所在目录的绝对路径（脚本在根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

# 激活 IndexTTS2 虚拟环境
cd "${INDEX_TTS_DIR}"
source .venv/bin/activate

# 设置环境变量
# 加载用户环境变量（包含DASHSCOPE_API_KEY等）
# 注意：~/.bashrc 在非交互式shell中会提前返回，所以直接读取并设置
# 优先使用已存在的环境变量，否则从 ~/.bashrc 读取
if [ -z "$DASHSCOPE_API_KEY" ] && [ -f ~/.bashrc ]; then
    # 读取 DASHSCOPE_API_KEY（如果存在）
    # 支持单引号和双引号两种格式
    DASHSCOPE_LINE=$(grep "^export DASHSCOPE_API_KEY=" ~/.bashrc | head -1)
    if [ -n "$DASHSCOPE_LINE" ]; then
        # 尝试提取单引号或双引号中的值
        DASHSCOPE_KEY=$(echo "$DASHSCOPE_LINE" | sed -n "s/.*['\"]\(.*\)['\"].*/\1/p")
        if [ -n "$DASHSCOPE_KEY" ]; then
            export DASHSCOPE_API_KEY="$DASHSCOPE_KEY"
        fi
    fi
fi

if [ -z "$HF_ENDPOINT" ] && [ -f ~/.bashrc ]; then
    # 读取 HF_ENDPOINT（如果存在）
    HF_ENDPOINT_LINE=$(grep "^export HF_ENDPOINT=" ~/.bashrc | head -1)
    if [ -n "$HF_ENDPOINT_LINE" ]; then
        HF_ENDPOINT_VAL=$(echo "$HF_ENDPOINT_LINE" | sed -n "s/.*['\"]\(.*\)['\"].*/\1/p")
        if [ -n "$HF_ENDPOINT_VAL" ]; then
            export HF_ENDPOINT="$HF_ENDPOINT_VAL"
        fi
    fi
fi

# 设置默认值（如果未从 ~/.bashrc 读取到）
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HOME="${INDEX_TTS_DIR}/.cache/hf"
export PYTHONUNBUFFERED=1
# 修复protobuf兼容性问题（IndexTTS2需要）
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

LLM_ENV_FILE="${PROJECT_ROOT}/.env"
if [ -n "${DASHSCOPE_API_KEY:-}" ]; then
    echo "✅ DASHSCOPE_API_KEY已设置（长度: ${#DASHSCOPE_API_KEY}）"
elif [ -f "${LLM_ENV_FILE}" ] && grep -Eq '^(LLM_API_KEY|LLM_API_KEY_ENV)=' "${LLM_ENV_FILE}"; then
    echo "✅ 检测到项目级 .env 翻译配置: ${LLM_ENV_FILE}"
else
    echo "⚠️  警告: 未检测到可用的翻译 LLM 凭据"
    echo "   可在 ${LLM_ENV_FILE} 中配置 LLM_API_KEY 或 LLM_API_KEY_ENV"
    echo "   也可在 ~/.bashrc 中设置: export DASHSCOPE_API_KEY='your-api-key'"
fi

# 为 NVIDIA 环境补充可选 CuDNN 路径；AMD/ROCm 和 CPU 环境保持系统默认配置
NVIDIA_CUDNN_DIR="${INDEX_TTS_DIR}/.venv/lib/python3.10/site-packages/nvidia/cudnn/lib"
if [ -d "${NVIDIA_CUDNN_DIR}" ]; then
    export LD_LIBRARY_PATH="${NVIDIA_CUDNN_DIR}:${LD_LIBRARY_PATH}"
fi

# 返回项目目录
cd "${PROJECT_ROOT}"

# 检查主项目额外依赖是否已安装
echo "🔍 检查主项目额外依赖..."
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements_project.txt"

check_dependency() {
    python -c "import $1" 2>/dev/null
    return $?
}

MISSING_DEPS=()

if [ -f "${PROJECT_ROOT}/config.yaml" ]; then
    WHISPER_BACKEND=$(grep -A 1 "^whisper:" "${PROJECT_ROOT}/config.yaml" | grep "backend:" | awk '{print $2}' | tr -d '"' || echo "faster-whisper")
else
    WHISPER_BACKEND="faster-whisper"
fi

if [ "$WHISPER_BACKEND" = "faster-whisper" ] || [ "$WHISPER_BACKEND" = "" ]; then
    if ! check_dependency "faster_whisper"; then
        MISSING_DEPS+=("faster-whisper")
    fi
else
    if ! check_dependency "whisper"; then
        MISSING_DEPS+=("openai-whisper")
    fi
fi

if ! check_dependency "scipy"; then MISSING_DEPS+=("scipy"); fi

if [ -f "${PROJECT_ROOT}/config.yaml" ]; then
    if grep -q "speaker_diarization:" "${PROJECT_ROOT}/config.yaml" || grep -q "multi_speaker" "${PROJECT_ROOT}/config.yaml"; then
        if ! check_dependency "pyannote"; then
            echo "⚠️  提示: 检测到说话人分离配置，但 pyannote.audio 未安装"
            echo "   如果不需要说话人分离功能，可以忽略此提示"
            echo "   如果需要，可以手动安装: pip install pyannote.audio"
        fi
    fi
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "❌ 检测到缺少以下依赖: ${MISSING_DEPS[*]}"
    echo ""
    echo "请先安装主项目依赖（环境配置时应该完成）："
    echo "  方式1（推荐）: ./scripts/install/install_with_uv.sh"
    echo "  方式2: cd ${INDEX_TTS_DIR} && uv pip install -r ${REQUIREMENTS_FILE}"
    echo ""
    echo "注意：依赖应该在环境配置时安装，而不是每次启动时安装。"
    echo "这样可以确保版本正确（如 numpy==1.26.2）并避免启动延迟。"
    exit 1
else
    echo "✅ 所有依赖已安装"
fi

# 检查并清理7861端口
echo "🔍 检查端口7861是否可用..."
PORT=7861
PID=$(lsof -ti :${PORT} 2>/dev/null)

if [ -n "$PID" ]; then
    echo "⚠️  端口${PORT}已被占用，进程ID: ${PID}"
    echo "🛑 正在终止占用端口的进程..."
    kill -9 ${PID} 2>/dev/null
    sleep 2
    
    # 再次检查是否成功kill
    PID_CHECK=$(lsof -ti :${PORT} 2>/dev/null)
    if [ -n "$PID_CHECK" ]; then
        echo "❌ 无法终止占用端口的进程，请手动检查: lsof -i :${PORT}"
        exit 1
    else
        echo "✅ 端口${PORT}已释放"
    fi
else
    echo "✅ 端口${PORT}可用"
fi

# 启动 Web UI
echo "🚀 启动音视频翻译 Web UI..."

export GRADIO_SERVER_PORT=7861
echo "🌐 启动Web UI，使用端口7861..."

mkdir -p "${PROJECT_ROOT}/data/logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
SYSTEM_LOG="${PROJECT_ROOT}/data/logs/system_${TIMESTAMP}.log"
echo "📝 系统日志将保存到: ${SYSTEM_LOG}"

# 使用新的媒体化入口
python media_translation_webui.py --host 0.0.0.0 --port 7861 --output-dir data/outputs --verbose --preload-models 2>&1 | tee "${SYSTEM_LOG}"
