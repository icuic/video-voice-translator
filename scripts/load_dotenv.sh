#!/bin/bash
# 从项目根目录的 .env 文件加载环境变量，source 式使用。
# 用法（在其他脚本开头）:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
#   source "${PROJECT_ROOT}/scripts/load_dotenv.sh"
#
# 规则:
#   * 只读取 <PROJECT_ROOT>/.env（如果存在）
#   * 注释行 (#...) 和空行跳过
#   * 支持 shell 引号: KEY="value"、KEY='value'、KEY=value
#   * 不覆盖进程中已显式设置过的同名环境变量（保证 docker/systemd/supervisor 的环境变量优先级最高）

: "${PROJECT_ROOT:=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

_load_dotenv_file() {
    local env_file="$1"
    [[ -f "${env_file}" ]] || return 0

    local line key value
    while IFS= read -r line || [[ -n "${line}" ]]; do
        # 去掉行首尾空白
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"

        # 空行 / 注释 跳过
        [[ -z "${line}" || "${line}" == \#* ]] && continue

        # 没有 = 号的非合规行跳过
        [[ "${line}" != *"="* ]] && continue

        key="${line%%=*}"
        value="${line#*=}"

        # key 去空白；value 去首尾空白；然后去首尾引号
        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"

        # 简单去掉首尾引号（仅当首尾都是同一种引号时），同时支持误写的反引号包裹
        if [[ "${value}" == \"*\" ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "${value}" == \'*\' ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "${#value}" -ge 2 && "${value:0:1}" == '`' && "${value:${#value}-1:1}" == '`' ]]; then
            # 用户误把 URL 写成 `https://...` 形式（反引号），这里按字面内容剥离，不做命令替换
            value="${value:1:${#value}-2}"
        fi

        # key 必须是合法的 shell 标识符
        [[ "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue

        # 不覆盖已存在于当前 shell 环境里的值
        # (间接判断: 通过参数展开 ${!varname+x} 检查是否被设置过)
        if [[ -z "${!key+x}" ]]; then
            # 安全赋值：用 printf 把 value 当作纯字面量转义后再 eval export，
            # 避免 value 内残留的 $/`` 被 shell 解释成命令替换/变量展开
            _escaped_value=$(printf '%s' "${value}" | sed "s/'/'\\\\''/g")
            eval "export ${key}='${_escaped_value}'"
        fi
    done < "${env_file}"
}

_load_dotenv_file "${PROJECT_ROOT}/.env"
unset -f _load_dotenv_file
