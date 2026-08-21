#!/bin/bash
# AI 音视频翻译系统 - MOTD 追加脚本
# 将项目的欢迎信息追加到系统 MOTD 末尾（不覆盖腾讯云原有 MOTD）
# 在 HAI 镜像首次启动时执行一次即可，也可以手动重跑。
#
# 用法：
#   sudo ./scripts/install/setup_motd.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJECT_DIR_NAME="$(basename "${PROJECT_ROOT}")"
MARKER_BEGIN="# ===== BEGIN video-voice-translator MOTD (DO NOT EDIT THIS BLOCK MANUALLY) ====="
MARKER_END="# ===== END video-voice-translator MOTD ===== "

MOTD_FILE="/etc/motd"
PROFILE_D_FILE="/etc/profile.d/video-voice-translator.sh"

COLOR_BOLD="\033[1m"
COLOR_GREEN="\033[32m"
COLOR_YELLOW="\033[33m"
COLOR_CYAN="\033[36m"
COLOR_RESET="\033[0m"

if [ "$(id -u)" -ne 0 ]; then
    echo "[ERR] 需要 root 权限修改 /etc/motd。请使用 sudo 运行：sudo $0" >&2
    exit 1
fi

PUBLIC_IP_PLACEHOLDER="<实例公网IP>"

BANNER=$(cat <<EOF
${COLOR_BOLD}╔════════════════════════════════════════════════════════════════╗${COLOR_RESET}
${COLOR_BOLD}║   AI 音视频翻译系统（HAI 镜像版 v1.0.0）                        ║${COLOR_RESET}
${COLOR_BOLD}╠════════════════════════════════════════════════════════════════╣${COLOR_RESET}
║   🌐  Web UI   : http://${PUBLIC_IP_PLACEHOLDER}:5173                            ║
║   📘  API Docs : http://${PUBLIC_IP_PLACEHOLDER}:8000/docs                        ║
║                                                                ║
║   ${COLOR_YELLOW}⚠️  首次使用必须配置 LLM 翻译密钥：${COLOR_RESET}                               ║
║                                                                ║
║   1) ${COLOR_GREEN}【推荐】${COLOR_RESET} 浏览器打开上面的 Web UI，自动引导页填写          ║
║   2) 或命令行执行： cd ~/${PROJECT_DIR_NAME} && ./configure.sh               ║
║                                                                ║
║   🔧  服务管理： cd ~/${PROJECT_DIR_NAME} && ./manage-supervisor.sh help     ║
║   🔄  更新代码： cd ~/${PROJECT_DIR_NAME} && ./update_project.sh             ║
${COLOR_BOLD}╚════════════════════════════════════════════════════════════════╝${COLOR_RESET}
EOF
)

TMP_FILE="$(mktemp)"
if [ -f "${MOTD_FILE}" ]; then
    awk -v m1="${MARKER_BEGIN}" -v m2="${MARKER_END}" '
        $0 == m1 { skip=1; next }
        $0 == m2 { skip=0; next }
        !skip { print }
    ' "${MOTD_FILE}" > "${TMP_FILE}"
else
    : > "${TMP_FILE}"
fi

{
    echo ""
    echo "${MARKER_BEGIN}"
    printf '%b\n' "${BANNER}"
    echo "${MARKER_END}"
} >> "${TMP_FILE}"

mv "${TMP_FILE}" "${MOTD_FILE}"
echo "[OK] 已更新 ${MOTD_FILE}"

cat > "${PROFILE_D_FILE}" << 'PROFILEEOF'
# video-voice-translator: 在用户交互式登录时动态替换 MOTD 中的 IP 占位符
# （/etc/motd 是静态文件，实例重启后的公网 IP 可能变化，这里动态修正一次）
case "$-" in
    *i*) ;;
    *) return ;;
esac

_place="<实例公网IP>"
_motd_file="/etc/motd"
_cache_key="/tmp/.vvt-motd-ip-hint"
if [ -f "${_motd_file}" ] && grep -q "${_place}" "${_motd_file}" 2>/dev/null; then
    _ip=""
    for _url in "http://metadata.tencentyun.com/latest/meta-data/public-ipv4" \
                "http://169.254.0.23/latest/meta-data/public-ipv4"; do
        _ip="$(curl -fsS --max-time 2 "${_url}" 2>/dev/null || true)"
        if [ -n "${_ip}" ]; then break; fi
    done
    if [ -z "${_ip}" ]; then
        _ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    fi
    if [ -n "${_ip}" ]; then
        _sig="${_ip}"
        if [ -f "${_cache_key}" ] && [ "$(cat "${_cache_key}" 2>/dev/null)" = "${_sig}" ]; then
            return 0
        fi
        if [ -w "${_motd_file}" ]; then
            if sed -i "s|${_place}|${_ip}|g" "${_motd_file}" 2>/dev/null; then
                echo "${_sig}" > "${_cache_key}" 2>/dev/null || true
            fi
        fi
    fi
fi
unset _place _motd_file _cache_key _ip _url _sig
PROFILEEOF
chmod 644 "${PROFILE_D_FILE}"
echo "[OK] 已写入 ${PROFILE_D_FILE}（首次登录自动填充真实公网 IP 到 MOTD）"

echo ""
echo "完成！下次 SSH 登录时即可看到 AI 音视频翻译系统的欢迎横幅。"
