#!/bin/bash
# 公共环境变量脚本 - 被后端启动脚本和 CLI 脚本统一 source.
# 使用方式: source scripts/setup_env.sh
#
# 优先级:
#   进程环境变量 (supervisor/docker/systemd)  >  项目根目录 .env  >  ~/.bashrc ~/.zshrc 兜底  >  脚本内置默认

if [ -z "${SETUP_ENV_SOURCED:-}" ]; then

# 路径
if [ -z "${PROJECT_ROOT:-}" ]; then
    if [ -n "${BASH_SOURCE[0]:-}" ]; then
        _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        PROJECT_ROOT="$(cd "${_SCRIPT_DIR}/.." && pwd)"
    else
        PROJECT_ROOT="$(pwd)"
    fi
fi
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

# 1) 项目 .env（优先级次于已经 export 的进程 env）
# shellcheck source=scripts/load_dotenv.sh
source "${PROJECT_ROOT}/scripts/load_dotenv.sh" 2>/dev/null || true

# 2) ~/.bashrc / ~/.zshrc 兜底（仅在值还没设置时读）
_SHELL_RC=""
if [ -z "${DASHSCOPE_API_KEY:-}" ] || [ -z "${HF_ENDPOINT:-}" ]; then
    if   [ -f ~/.bashrc ]; then _SHELL_RC=~/.bashrc
    elif [ -f ~/.zshrc ];  then _SHELL_RC=~/.zshrc
    fi
fi
_read_env_from_rc() {
    local var_name="$1"
    [ -z "${!var_name:-}" ] || return 0
    [ -n "${_SHELL_RC}" ] || return 0
    local line val
    line=$(grep "^export ${var_name}=" "$_SHELL_RC" 2>/dev/null | head -1) || true
    [ -n "${line}" ] || return 0
    val=$(echo "$line" | sed -n "s/.*['\"]\(.*\)['\"].*/\1/p")
    if [ -z "${val}" ]; then
        val=$(echo "$line" | sed -n "s/^export ${var_name}=\(.*\)$/\1/p" | tr -d "'\"")
    fi
    [ -n "${val}" ] && export "${var_name}=${val}" || true
}
_read_env_from_rc "DASHSCOPE_API_KEY"
_read_env_from_rc "HF_ENDPOINT"
unset -f _read_env_from_rc
unset _SHELL_RC

# 3) 强制默认值（仅变量还为空时设）
#    HF_ENDPOINT：留空直连官方 huggingface.co（当前环境直连 200 OK，比部分仓库 308 回源的镜像更稳）
#    如需使用国内镜像，可在 .env 里显式设置: HF_ENDPOINT=https://hf-mirror.com
if [ -z "${HF_ENDPOINT:-}" ]; then
    unset HF_ENDPOINT
fi
export HF_HOME="${INDEX_TTS_DIR}/.cache/hf"
export PYTHONUNBUFFERED=1
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

# CUDA / CuDNN 运行时库路径（探测虚拟环境里的 python 子目录，自动支持 3.10/3.11/3.12）
if [ -d "${INDEX_TTS_DIR}/.venv/lib" ]; then
    _PY_VER=$(ls "${INDEX_TTS_DIR}/.venv/lib" 2>/dev/null | grep '^python3\.' | head -1) || true
    if [ -n "${_PY_VER}" ]; then
        export LD_LIBRARY_PATH="${INDEX_TTS_DIR}/.venv/lib/${_PY_VER}/site-packages/nvidia/cudnn/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
    fi
fi
export PATH="/usr/local/cuda/bin:${PATH:-}"

export SETUP_ENV_SOURCED=1
export PROJECT_ROOT
export INDEX_TTS_DIR

fi
