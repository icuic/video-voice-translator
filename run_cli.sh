#!/bin/bash

# 音视频翻译命令行工具启动脚本

echo "🎬 启动音视频翻译命令行工具..."

# 获取脚本所在目录的绝对路径（脚本在根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

# 激活 IndexTTS2 虚拟环境
if [ ! -d "${INDEX_TTS_DIR}/.venv" ]; then
    echo "❌ 虚拟环境不存在，请先安装 index-tts 依赖"
    echo "   运行: cd index-tts && uv sync"
    exit 1
fi

cd "${INDEX_TTS_DIR}"
source .venv/bin/activate

# 设置环境变量
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HOME="${INDEX_TTS_DIR}/.cache/hf"
export PYTHONUNBUFFERED=1

# CUDA/CuDNN 运行时库路径
export LD_LIBRARY_PATH="${INDEX_TTS_DIR}/.venv/lib/python3.10/site-packages/nvidia/cudnn/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"
export PATH="/usr/local/cuda/bin:${PATH}"

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
    echo "⚠️  检测到缺少以下依赖: ${MISSING_DEPS[*]}"
    echo "📦 正在安装主项目额外依赖..."
    pip install -q -r "${REQUIREMENTS_FILE}"
    if [ $? -eq 0 ]; then
        echo "✅ 依赖安装完成"
    else
        echo "❌ 依赖安装失败，请手动执行: pip install -r ${REQUIREMENTS_FILE}"
        exit 1
    fi
else
    echo "✅ 所有依赖已安装"
fi

# 创建日志目录
mkdir -p "${PROJECT_ROOT}/data/logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
SYSTEM_LOG="${PROJECT_ROOT}/data/logs/system_${TIMESTAMP}.log"
echo "📝 系统日志将保存到: ${SYSTEM_LOG}"

# 执行翻译命令，传递所有参数（同时输出到终端和日志文件）
echo "🚀 执行翻译命令..."
python media_translation_cli.py "$@" 2>&1 | tee "${SYSTEM_LOG}"

