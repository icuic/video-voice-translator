#!/bin/bash

# 音视频翻译 Web UI 演示版启动脚本

echo "🎬 启动音视频翻译 Web UI 演示版..."

# 获取脚本所在目录的绝对路径（脚本在根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

# 激活 IndexTTS2 虚拟环境
cd "${INDEX_TTS_DIR}"
source .venv/bin/activate

# 返回项目目录
cd "${PROJECT_ROOT}"

# 检查并清理7862端口
PORT=7862
echo "🔍 检查端口 ${PORT} 是否可用..."

# 查找占用7862端口的进程
PID=$(lsof -ti:${PORT} 2>/dev/null)

if [ -n "$PID" ]; then
    echo "⚠️  检测到端口 ${PORT} 被进程 ${PID} 占用"
    echo "🔄 正在终止进程 ${PID}..."
    kill -9 ${PID} 2>/dev/null
    sleep 2
    
    # 再次检查是否成功释放
    PID_CHECK=$(lsof -ti:${PORT} 2>/dev/null)
    if [ -n "$PID_CHECK" ]; then
        echo "❌ 无法释放端口 ${PORT}，请手动检查"
        exit 1
    else
        echo "✅ 端口 ${PORT} 已成功释放"
    fi
else
    echo "✅ 端口 ${PORT} 可用"
fi

# 启动演示 Web UI
echo "🚀 启动演示 Web UI..."
echo "⚠️  注意：此界面仅用于演示UI布局和功能，不包含实际翻译功能"

export GRADIO_SERVER_PORT=${PORT}
echo "🌐 启动Web UI，使用端口 ${PORT}..."

# 启动演示UI
python demo_webui.py

