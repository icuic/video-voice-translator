#!/bin/bash
# 公共环境变量脚本 - 被后端启动脚本和 CLI 脚本统一 source
# 使用方式：source scripts/setup_env.sh
# 注意：调用前必须确保已经 cd 到项目根目录

if [ -z "$SETUP_ENV_SOURCED" ]; then

# -------------------- 路径计算 --------------------
# 找到项目根目录：调用此脚本的入口脚本可能位于任意层级，这里向上回溯找包含 index-tts 的目录
if [ -z "$PROJECT_ROOT" ]; then
    if [ -n "${BASH_SOURCE[0]}" ]; then
        _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        PROJECT_ROOT="$(cd "${_SCRIPT_DIR}/.." && pwd)"
    else
        PROJECT_ROOT="$(pwd)"
    fi
fi
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

# -------------------- 从 ~/.bashrc / ~/.zshrc 读取环境变量 --------------------
# 支持 bash / zsh
_SHELL_RC=""
if [ -f ~/.bashrc ]; then
    _SHELL_RC=~/.bashrc
elif [ -f ~/.zshrc ]; then
    _SHELL_RC=~/.zshrc
fi

_read_env_from_rc() {
    local var_name="$1"
    if [ -n "$_SHELL_RC" ] && [ -z "$(eval echo \${$var_name:-})" ]; then
        local line
        line=$(grep "^export ${var_name}=" "$_SHELL_RC" 2>/dev/null | head -1)
        if [ -n "$line" ]; then
            local val
            val=$(echo "$line" | sed -n "s/.*['\"]\(.*\)['\"].*/\1/p")
            if [ -z "$val" ]; then
                val=$(echo "$line" | sed -n "s/^export ${var_name}=\(.*\)$/\1/p" | tr -d "'\"")
            fi
            if [ -n "$val" ]; then
                export "${var_name}=${val}"
            fi
        fi
    fi
}

_read_env_from_rc "DASHSCOPE_API_KEY"
_read_env_from_rc "HF_ENDPOINT"

# -------------------- 项目强制环境变量 --------------------
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HOME="${INDEX_TTS_DIR}/.cache/hf"
export PYTHONUNBUFFERED=1
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

# CUDA / CuDNN 运行时库路径（优先使用虚拟环境中安装的 nvidia 库）
if [ -d "${INDEX_TTS_DIR}/.venv/lib" ]; then
    _PY_VER=$(ls "${INDEX_TTS_DIR}/.venv/lib" 2>/dev/null | grep "^python3" | head -1)
    if [ -n "$_PY_VER" ]; then
        export LD_LIBRARY_PATH="${INDEX_TTS_DIR}/.venv/lib/${_PY_VER}/site-packages/nvidia/cudnn/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"
    fi
fi
export PATH="/usr/local/cuda/bin:${PATH}"

# 标记已经 source 过，避免重复执行
export SETUP_ENV_SOURCED=1
export PROJECT_ROOT
export INDEX_TTS_DIR

fi
