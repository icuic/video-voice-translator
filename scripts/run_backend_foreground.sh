#!/bin/bash
# 后端服务前台启动脚本（专供 supervisord 调用，也可手动前台运行）
# - 前台运行（不 detach）
# - 日志输出到 stdout/stderr，让 supervisord 接管
# - 不使用 --reload（生产模式），如需热重载请用 DEV_MODE=1

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

# 加载公共环境
source "${PROJECT_ROOT}/scripts/setup_env.sh"

# 二次兜底强制注入 LLM 环境：
# 在启动 uvicorn 之前，再次从磁盘 .env 文件把 LLM_* / DASHSCOPE_* 显式 export 一遍，
# 并把当前值（脱敏）打印到 stdout → 最终会落到 backend.log。
# 目的：100% 保证"磁盘 .env 写了 → uvicorn 进程环境一定有值"。
# （之前真实验证过：/proc/<uvicorn pid>/environ 里只有 PROJECT_ROOT 没有 LLM_*，导致翻译期 os.getenv 失败）
_force_inject_llm_env_and_log() {
    local env_file="${PROJECT_ROOT}/.env"
    local line key value
    local -a WANTED_KEYS=(
        LLM_BASE_URL LLM_API_KEY LLM_MODEL LLM_TEMPERATURE LLM_TIMEOUT DASHSCOPE_API_KEY
    )
    if [ -f "${env_file}" ]; then
        while IFS= read -r line || [ -n "${line}" ]; do
            line="${line#"${line%%[![:space:]]*}"}"
            line="${line%"${line##*[![:space:]]}"}"
            [ -z "${line}" ] && continue
            [[ "${line}" == \#* ]] && continue
            [[ "${line}" != *"="* ]] && continue
            key="${line%%=*}"
            value="${line#*=}"
            key="${key#"${key%%[![:space:]]*}"}"
            key="${key%"${key##*[![:space:]]}"}"
            value="${value#"${value%%[![:space:]]*}"}"
            value="${value%"${value##*[![:space:]]}"}"
            if [ "${#value}" -ge 2 ]; then
                case "${value}" in
                    \"*\"|\'*\'|\`*\`)
                        value="${value:1:${#value}-2}"
                        ;;
                esac
            fi
            case "${key}" in
                LLM_BASE_URL|LLM_API_KEY|LLM_MODEL|LLM_TEMPERATURE|LLM_TIMEOUT|DASHSCOPE_API_KEY)
                    ;;
                *) continue ;;
            esac
            if [ -z "${!key:-}" ]; then
                eval "export ${key}=\"\${value}\""
            fi
        done < "${env_file}"
    fi

    local k masked
    echo "[supervisord:backend] setup_env_sh 注入结果:"
    for k in "${WANTED_KEYS[@]}"; do
        if [ -n "${!k:-}" ]; then
            case "${k}" in
                *API_KEY|*API_SECRET)
                    local raw="${!k}"
                    if [ "${#raw}" -le 8 ]; then
                        masked="***"
                    else
                        masked="${raw:0:4}…${raw:${#raw}-4}"
                    fi
                    ;;
                *) masked="${!k}" ;;
            esac
            echo "[supervisord:backend]   setup_env_sh:${k}=${masked}"
        else
            echo "[supervisord:backend]   setup_env_sh:${k}=<empty>"
        fi
    done
}
_force_inject_llm_env_and_log
unset -f _force_inject_llm_env_and_log

# 检查虚拟环境
if [ ! -d "${INDEX_TTS_DIR}/.venv" ]; then
    echo "[supervisord:backend] ERROR: 虚拟环境不存在，请先安装 index-tts 依赖" >&2
    echo "   cd index-tts && uv sync" >&2
    exit 1
fi

# 进入项目根目录
cd "${PROJECT_ROOT}"

# 监听地址和端口（可通过环境变量覆盖）
HOST="${BACKEND_HOST:-0.0.0.0}"
PORT="${BACKEND_PORT:-8000}"

# 是否为开发模式（默认生产模式不开 reload）
if [ "$DEV_MODE" = "1" ]; then
    RELOAD_FLAG="--reload"
    echo "[supervisord:backend] 启动后端（开发模式，已开启 reload）: ${HOST}:${PORT}"
else
    RELOAD_FLAG=""
    echo "[supervisord:backend] 启动后端（生产模式）: ${HOST}:${PORT}"
fi

# 使用虚拟环境中的 Python 执行 uvicorn（前台运行，不要加 &）
# 关键：用 env 命令把 LLM_* 显式挂到新进程的环境表上，确保 /proc/<pid>/environ 一定能看到，
# 彻底避免 supervisor + source setup_env.sh + exec 的某些组合下"父 shell 有 export 但子进程列表没显示"的问题。
# 然后再交给 main.py 层再次从磁盘 .env 强制写入 os.environ，形成双保险。
_FORCE_ENV_ARGS=()
for k in LLM_BASE_URL LLM_API_KEY LLM_MODEL LLM_TEMPERATURE LLM_TIMEOUT DASHSCOPE_API_KEY MIRROR_MODE HF_ENDPOINT USE_MODELSCOPE PROJECT_ROOT INDEX_TTS_DIR HOME USER USERNAME LOGNAME PATH LANG LC_ALL TZ PYTHONPATH VIRTUAL_ENV; do
  if [ -n "${!k:-}" ]; then
    _FORCE_ENV_ARGS+=("${k}=${!k}")
  fi
done
echo "[supervisord:backend] 启动 uvicorn 时强制注入环境变量数量: ${#_FORCE_ENV_ARGS[@]}"
exec env \
  "${_FORCE_ENV_ARGS[@]}" \
  "${INDEX_TTS_DIR}/.venv/bin/python" -m uvicorn backend.app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    $RELOAD_FLAG \
    --limit-max-requests 1000 \
    --timeout-keep-alive 300 \
    --limit-concurrency 1000 \
    --backlog 2048
