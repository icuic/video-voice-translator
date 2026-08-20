#!/bin/bash
# 一键安装脚本 - 全程无交互，所有用户配置从项目根目录的 .env 文件读取。
#
# 前置步骤（必做）:
#   cp .env.example .env
#   # 然后编辑 .env，至少填写 DASHSCOPE_API_KEY，MIRROR_MODE 推荐填 tencent-intranet（腾讯云 ECS）
#
# 用法:
#   ./install_all.sh                        # 读取 .env 里的 MIRROR_MODE（没有则默认 auto）
#   ./install_all.sh --mirror tencent       # CLI 覆盖 .env 的镜像模式
#   ./install_all.sh -h                     # 帮助

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
cd "${PROJECT_ROOT}"

# ============================================================
# A. 加载 .env（优先级最低，CLI 和 进程 env 覆盖）
# ============================================================
# shellcheck source=scripts/load_dotenv.sh
source "${PROJECT_ROOT}/scripts/load_dotenv.sh"

# ============================================================
# B. 帮助 & 参数解析（CLI 优先级最高）
# ============================================================
show_help() {
    cat <<'EOF'
用法: ./install_all.sh [选项]

[ 前置 ] 先填写项目根目录的 .env（cp .env.example .env）
  必填: DASHSCOPE_API_KEY
  推荐: MIRROR_MODE  (腾讯云 ECS 填 tencent-intranet)

选项:
  --mirror <tencent-intranet|tencent|china|official|auto>
        tencent-intranet  腾讯云 ECS 内网源 ✨ 推荐（不走公网流量）
        tencent           腾讯云公网镜像
        china             阿里云 + 清华镜像（国内通用）
        official          PyPI / NPM / HF 官方源（海外服务器）
        auto              默认: 依次探测 tencent-intranet -> tencent -> china -> official
  -h, --help
        显示本帮助

示例:
  ./install_all.sh
  ./install_all.sh --mirror tencent-intranet
  ./install_all.sh --mirror official
EOF
}

# CLI 参数优先覆盖 .env 里的 MIRROR_MODE
MIRROR_MODE_CLI=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mirror)
            [[ $# -lt 2 ]] && { echo "❌ --mirror 需要参数"; exit 1; }
            MIRROR_MODE_CLI="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "❌ 未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

MIRROR_MODE="${MIRROR_MODE_CLI:-${MIRROR_MODE:-auto}}"
case "${MIRROR_MODE}" in
    tencent-intranet|tencent|china|official|auto) ;;
    *)
        echo "❌ 非法 --mirror=${MIRROR_MODE}；可取值: tencent-intranet | tencent | china | official | auto"
        exit 1
        ;;
esac

# ============================================================
# C. 全局超时
# ============================================================
CURL_RETRY_ALL_ERRORS=""
if curl --help all 2>/dev/null | grep -q -- "--retry-all-errors"; then
    CURL_RETRY_ALL_ERRORS="--retry-all-errors"
fi
export CURL_ARGS="--connect-timeout 10 --max-time 120 --retry 3 --retry-delay 2 ${CURL_RETRY_ALL_ERRORS} --fail --silent --show-error --location"
export GIT_HTTP_LOW_SPEED_LIMIT=1000
export GIT_HTTP_LOW_SPEED_TIME=30
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-120}"
export NPM_CONFIG_FETCH_TIMEOUT=120000

# ============================================================
# D. 预设 5 组镜像（允许用户在 .env 里直接覆盖 UV_DEFAULT_INDEX / NPM_REGISTRY / NODE_SETUP_URL / HF_ENDPOINT）
# ============================================================
# 1) 腾讯云 ECS 内网 (免公网流量，仅腾讯云同地域 ECS 可解析 mirrors.tencentyun.com)
#    npm 内网腾讯没镜像，回退到公网 mirrors.cloud.tencent.com/npm
#    HF：默认直连官方（hf-mirror 对部分仓库 308 回源反而不稳；如需镜像，在 .env 里显式写 HF_ENDPOINT=https://hf-mirror.com）
GROUP_TENCENT_INTRANET_PYPI="http://mirrors.tencentyun.com/pypi/simple"
GROUP_TENCENT_INTRANET_NPM="https://mirrors.cloud.tencent.com/npm/"
GROUP_TENCENT_INTRANET_HF=""
GROUP_TENCENT_INTRANET_NODE="https://deb.nodesource.com/setup_20.x"

# 2) 腾讯云公网
GROUP_TENCENT_PYPI="https://mirrors.cloud.tencent.com/pypi/simple"
GROUP_TENCENT_NPM="https://mirrors.cloud.tencent.com/npm/"
GROUP_TENCENT_HF=""
GROUP_TENCENT_NODE="https://deb.nodesource.com/setup_20.x"

# 3) 国内通用（阿里云 + 官方 Nodesource）
GROUP_CHINA_PYPI="https://mirrors.aliyun.com/pypi/simple"
GROUP_CHINA_NPM="https://registry.npmmirror.com"
GROUP_CHINA_HF=""
GROUP_CHINA_NODE="https://deb.nodesource.com/setup_20.x"

# 4) 官方
GROUP_OFFICIAL_PYPI="https://pypi.org/simple"
GROUP_OFFICIAL_NPM="https://registry.npmjs.org"
GROUP_OFFICIAL_HF="https://huggingface.co"
GROUP_OFFICIAL_NODE="https://deb.nodesource.com/setup_20.x"

# ============================================================
# E. 探测函数
# ============================================================
ping_url() {
    local url="$1" t
    t=$(curl --connect-timeout 5 --max-time 8 -s -o /dev/null -w "%{time_total}" "${url}" 2>/dev/null || true)
    if [[ -n "${t}" && "${t}" != "0" ]]; then
        awk -v v="${t}" 'BEGIN{ printf "%d\n", v*1000 }'
    else
        echo ""
    fi
}

pick_fastest_of_two() {
    local name="$1" a_ms="$2" a_url="$3" b_ms="$4" b_url="$5" ms url n
    if [[ -n "${a_ms}" && -n "${b_ms}" ]]; then
        if (( a_ms <= b_ms )); then ms="${a_ms}"; url="${a_url}"; n="A"; else ms="${b_ms}"; url="${b_url}"; n="B"; fi
    elif [[ -n "${a_ms}" ]]; then ms="${a_ms}"; url="${a_url}"; n="A"
    elif [[ -n "${b_ms}" ]]; then ms="${b_ms}"; url="${b_url}"; n="B"
    else ms=""; url="${a_url}"; n="A"; echo "    ⚠️  ${name}: 都探测失败，兜底 A"; fi
    if [[ -n "${ms}" ]]; then echo "    ✅ ${name}: ${n} (${ms}ms) ${url}"; fi
    echo "${url}"
}

# ============================================================
# F. 决定镜像组
# ============================================================
echo "=========================================="
echo "🚀 Video Voice Translator - 一键安装（无交互）"
echo "=========================================="
echo "  .env 文件: ${PROJECT_ROOT}/.env $([[ -f "${PROJECT_ROOT}/.env" ]] && echo ✅ 已加载 || echo ⚠️  未提供（先 cp .env.example .env）)"
[[ -z "${DASHSCOPE_API_KEY}" ]] && echo "  ⚠️  DASHSCOPE_API_KEY 未设置（翻译功能运行时需要；.env 里填好再 manage-supervisor restart 即可）"
echo "  镜像模式: ${MIRROR_MODE}"
echo ""

echo "🔎  解析最终镜像..."
apply_group() {
    local pypi="$1" npmr="$2" hf="$3" node="$4"
    UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-${pypi}}"
    NPM_REGISTRY="${NPM_REGISTRY:-${npmr}}"
    if [ -z "${HF_ENDPOINT:-}" ] && [ -n "${hf}" ]; then
        HF_ENDPOINT="${hf}"
    elif [ -z "${HF_ENDPOINT:-}" ] && [ -z "${hf}" ]; then
        # 预设里故意留空 → 直连官方 huggingface.co（比部分仓库 308 回源的镜像更稳）
        unset HF_ENDPOINT
    fi
    NODE_SETUP_URL="${NODE_SETUP_URL:-${node}}"
}

if [[ "${MIRROR_MODE}" == "tencent-intranet" ]]; then
    echo "  使用预设: tencent-intranet"
    apply_group "${GROUP_TENCENT_INTRANET_PYPI}" "${GROUP_TENCENT_INTRANET_NPM}" "${GROUP_TENCENT_INTRANET_HF}" "${GROUP_TENCENT_INTRANET_NODE}"
elif [[ "${MIRROR_MODE}" == "tencent" ]]; then
    echo "  使用预设: tencent"
    apply_group "${GROUP_TENCENT_PYPI}" "${GROUP_TENCENT_NPM}" "${GROUP_TENCENT_HF}" "${GROUP_TENCENT_NODE}"
elif [[ "${MIRROR_MODE}" == "china" ]]; then
    echo "  使用预设: china"
    apply_group "${GROUP_CHINA_PYPI}" "${GROUP_CHINA_NPM}" "${GROUP_CHINA_HF}" "${GROUP_CHINA_NODE}"
elif [[ "${MIRROR_MODE}" == "official" ]]; then
    echo "  使用预设: official"
    apply_group "${GROUP_OFFICIAL_PYPI}" "${GROUP_OFFICIAL_NPM}" "${GROUP_OFFICIAL_HF}" "${GROUP_OFFICIAL_NODE}"
else
    # auto: 探测 4 组，每组 ping 各自的 PyPI；然后取最快的组
    echo "  auto 模式: 探测 PyPI + NodeSetup + HF + NPM 综合最快组..."
    for g in TENCENT_INTRANET TENCENT CHINA OFFICIAL; do
        pypi_var="GROUP_${g}_PYPI"; npm_var="GROUP_${g}_NPM"; hf_var="GROUP_${g}_HF"; node_var="GROUP_${g}_NODE"
        t1=$(ping_url "${!pypi_var}")
        t2=$(ping_url "${!npm_var}")
        t3=$(ping_url "${!hf_var}")
        t4=$(ping_url "${!node_var}")
        sum=0; n=0
        for v in "${t1}" "${t2}" "${t3}" "${t4}"; do [[ -n "${v}" ]] && { sum=$((sum+v)); n=$((n+1)); }; done
        if (( n > 0 )); then
            avg=$(( sum / n ))
        else
            avg=999999
        fi
        declare "SCORE_${g}=${avg}"
        declare "COUNT_${g}=${n}"
        echo "    组 ${g}: 可达 ${n}/4 → 平均 ${avg}ms"
    done
    # 找可达最多的组；并列选平均最小
    best="" best_avg=999999 best_n=-1
    for g in TENCENT_INTRANET TENCENT CHINA OFFICIAL; do
        count_ref="COUNT_${g}"; score_ref="SCORE_${g}"
        n="${!count_ref}"; s="${!score_ref}"
        if (( n > best_n )) || { (( n == best_n )) && (( s < best_avg )); }; then
            best_n="${n}"; best_avg="${s}"; best="${g}"
        fi
    done
    echo "  🏁 auto 选择: ${best} (可达 ${best_n}/4，平均 ${best_avg}ms)"
    pypi_var="GROUP_${best}_PYPI"; npm_var="GROUP_${best}_NPM"; hf_var="GROUP_${best}_HF"; node_var="GROUP_${best}_NODE"
    apply_group "${!pypi_var}" "${!npm_var}" "${!hf_var}" "${!node_var}"
fi

# 汇总确认
echo ""
echo "🎯 最终使用:"
echo "   UV_DEFAULT_INDEX = ${UV_DEFAULT_INDEX}"
echo "   NPM_REGISTRY     = ${NPM_REGISTRY}"
echo "   HF_ENDPOINT      = ${HF_ENDPOINT:-（直连官方 https://huggingface.co）}"
echo "   NODE_SETUP_URL   = ${NODE_SETUP_URL}"
echo ""
[[ -z "${DASHSCOPE_API_KEY}" ]] && echo "⚠️  运行时必填 DASHSCOPE_API_KEY 未设置（.env 填好后 ./manage-supervisor restart 即可生效）"

# 导出
export EFFECTIVE_MIRROR="${MIRROR_MODE}"
export UV_DEFAULT_INDEX NPM_REGISTRY HF_ENDPOINT NODE_SETUP_URL UV_HTTP_TIMEOUT NPM_CONFIG_FETCH_TIMEOUT CURL_ARGS GIT_HTTP_LOW_SPEED_LIMIT GIT_HTTP_LOW_SPEED_TIME

# sudo
if [ "$EUID" -eq 0 ]; then SUDO_CMD=""; else SUDO_CMD="sudo"; fi

# ============================================================
# E1. uv 自举（新装裸机最容易踩的坑：uv: command not found）
#     install_with_uv_china.sh / install_with_uv_official.sh / install_index_tts.sh
#     自己也有 uv 安装，但父脚本这里统一保证 PATH 里有 uv，子脚本就不会再各自跑
#     curl 安装；同时 china/official 用不同的 UV_INSTALL_DOWNLOAD_URL 镜像。
# ============================================================
ensure_uv_installed() {
    # 如果当前 shell 找不到 uv，但 ~/.local/bin/uv 已经存在，则优先补 PATH
    if ! command -v uv &>/dev/null && [ -x "$HOME/.local/bin/uv" ]; then
        export PATH="$HOME/.local/bin:${PATH}"
    fi
    if command -v uv &>/dev/null; then
        echo "✅ uv: $(uv --version 2>/dev/null | head -1 || echo OK)"
        return 0
    fi
    echo "📦 安装 uv 包管理器..."
    local uv_installer_url
    case "${MIRROR_MODE}" in
        tencent*|china)
            # 国内镜像：BFSU mirrors 走 astral-sh/uv 的 GitHub release 镜像（astral.sh 官方站在国内有时会 403/超时）
            if [ -n "${UV_INSTALL_URL:-}" ]; then
                uv_installer_url="${UV_INSTALL_URL}"
            else
                uv_installer_url="https://mirrors.bfsu.edu.cn/github-release/astral-sh/uv/LatestRelease/uv-installer.sh"
            fi
            # 镜像站如果不可用（例如首次下载脚本 404/超时），fallback 回官方 astral.sh 原版
            set +e
            TMP_INSTALLER="$(mktemp)"
            if curl ${CURL_ARGS} -o "${TMP_INSTALLER}" "${uv_installer_url}"; then
                sh "${TMP_INSTALLER}" 2>&1 | tail -5 || {
                    echo "⚠️  国内镜像 uv installer 失败，回退 astral.sh 官方..."
                    rm -f "${TMP_INSTALLER}"
                    curl -LsSf https://astral.sh/uv/install.sh | sh
                }
            else
                echo "⚠️  国内镜像 uv installer 下载失败（${uv_installer_url}），回退 astral.sh 官方..."
                rm -f "${TMP_INSTALLER}"
                curl -LsSf https://astral.sh/uv/install.sh | sh
            fi
            set -e
            rm -f "${TMP_INSTALLER}"
            ;;
        *)
            curl -LsSf https://astral.sh/uv/install.sh | sh
            ;;
    esac
    export PATH="$HOME/.local/bin:${PATH}"
    # 再校验一次
    if command -v uv &>/dev/null; then
        echo "✅ uv: $(uv --version 2>/dev/null | head -1 || echo OK)"
    else
        echo "❌ uv 安装失败（PATH=$PATH）；请手动执行: curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.bashrc"
        exit 1
    fi
}
ensure_uv_installed

# ============================================================
# 步骤1: 系统依赖 (FFmpeg / lsof / Node.js / Supervisor)
# ============================================================
echo ""
echo "=========================================="
echo "📦 步骤 1/8: 安装系统依赖"
echo "=========================================="

if ! command -v ffmpeg &>/dev/null; then
    echo "安装 FFmpeg..."
    $SUDO_CMD apt-get update -qq
    $SUDO_CMD apt-get install -y ffmpeg
fi
echo "✅ FFmpeg: $(ffmpeg -version 2>/dev/null | head -1 || echo OK)"

if ! command -v lsof &>/dev/null; then
    echo "安装 lsof..."
    $SUDO_CMD apt-get install -y lsof
fi
echo "✅ lsof: OK"

if ! command -v node &>/dev/null; then
    echo "安装 Node.js 20.x (${NODE_SETUP_URL})..."
    TMP_NODE_SETUP="$(mktemp)"
    if curl ${CURL_ARGS} -o "${TMP_NODE_SETUP}" "${NODE_SETUP_URL}"; then
        $SUDO_CMD bash "${TMP_NODE_SETUP}"
        $SUDO_CMD apt-get install -y nodejs
        rm -f "${TMP_NODE_SETUP}"
    else
        rm -f "${TMP_NODE_SETUP}"
        echo "❌ Node.js setup 脚本下载超时。可手动安装或切换 --mirror official"
        exit 1
    fi
fi
echo "✅ Node.js: $(node --version 2>/dev/null || echo OK)"

if ! command -v supervisord &>/dev/null; then
    echo "安装 supervisor..."
    $SUDO_CMD apt-get update -qq
    $SUDO_CMD apt-get install -y supervisor
    echo "禁用系统全局 supervisord（避免冲突）"
    $SUDO_CMD systemctl stop supervisor 2>/dev/null || true
    $SUDO_CMD systemctl disable supervisor 2>/dev/null || true
else
    if systemctl is-active --quiet supervisor 2>/dev/null; then
        echo "⚠️  系统全局 supervisor 正在运行；本项目使用 ./manage-supervisor.sh 管理"
    fi
fi
echo "✅ supervisor: $(supervisord --version 2>/dev/null || echo OK)"

# ============================================================
# 步骤2: IndexTTS2
# ============================================================
echo ""
echo "=========================================="
echo "📦 步骤 2/8: 安装 IndexTTS2（含模型下载，~5.5GB）"
echo "=========================================="
bash "${PROJECT_ROOT}/scripts/install/install_index_tts.sh"

# ============================================================
# 步骤3: 检查 PyTorch
# ============================================================
echo ""
echo "=========================================="
echo "🔍 步骤 3/8: 检查 PyTorch"
echo "=========================================="
if [ -f "${PROJECT_ROOT}/index-tts/.venv/bin/activate" ]; then
    cd "${PROJECT_ROOT}/index-tts"
    source .venv/bin/activate
    if python -c "import torch; print(f'✅ PyTorch {torch.__version__} | CUDA={torch.cuda.is_available()}')" 2>/dev/null; then
        :
    else
        echo "⚠️  PyTorch 暂不可用，依赖安装阶段会再次尝试"
    fi
    cd "${PROJECT_ROOT}"
else
    echo "⚠️  index-tts 虚拟环境未创建，跳过"
fi

# ============================================================
# 步骤4: 主项目 Python 依赖
# ============================================================
echo ""
echo "=========================================="
echo "📦 步骤 4/8: 安装主项目额外依赖"
echo "=========================================="
case "${MIRROR_MODE}" in
    tencent*|china)
        INSTALL_UV_SCRIPT="${PROJECT_ROOT}/scripts/install/install_with_uv_china.sh"
        # 注：china 脚本优先用环境变量 UV_DEFAULT_INDEX，所以 tencent-intranet 也能用
        ;;
    *)
        INSTALL_UV_SCRIPT="${PROJECT_ROOT}/scripts/install/install_with_uv_official.sh"
        ;;
esac
echo "使用: ${INSTALL_UV_SCRIPT}"
[ -f "${INSTALL_UV_SCRIPT}" ] || { echo "❌ 找不到脚本"; exit 1; }
bash "${INSTALL_UV_SCRIPT}"

# ============================================================
# 步骤5: 前端依赖
# ============================================================
echo ""
echo "=========================================="
echo "📦 步骤 5/8: 安装前端依赖 (npm)"
echo "=========================================="
command -v npm &>/dev/null || { echo "❌ npm 未安装"; exit 1; }
[ -d "${PROJECT_ROOT}/frontend" ] || { echo "❌ frontend 目录缺失"; exit 1; }
cd "${PROJECT_ROOT}/frontend"
NPM_ARGS="--fetch-timeout=120000 --no-audit --no-fund --registry=${NPM_REGISTRY}"
if [ ! -d "node_modules" ]; then
    echo "npm install (registry=${NPM_REGISTRY})"
    # shellcheck disable=SC2086
    npm install ${NPM_ARGS}
else
    echo "✅ 已存在 frontend/node_modules；如需重装请删除该目录后重跑"
fi
cd "${PROJECT_ROOT}"

# ============================================================
# 步骤6: 最终验证 + 完成
# ============================================================
echo ""
echo "=========================================="
echo "✅ 步骤 6/8: 最终验证"
echo "=========================================="
cd "${PROJECT_ROOT}/index-tts"
source .venv/bin/activate
cd "${PROJECT_ROOT}"

if python tools/check_dependencies.py 2>/dev/null; then
    echo "✅ check_dependencies.py 通过"
else
    echo "⚠️  check_dependencies.py 部分不通过"
fi
python -c "from indextts.infer_v2 import IndexTTS2; print('✅ IndexTTS2 导入 OK')" 2>/dev/null || echo "⚠️  IndexTTS2 导入未就绪（模型未下载完成？）"
if [ -f "${PROJECT_ROOT}/index-tts/checkpoints/gpt.pth" ] && [ -f "${PROJECT_ROOT}/index-tts/checkpoints/s2mel.pth" ]; then
    echo "✅ 模型文件已就绪"
else
    echo "⚠️  模型文件缺失；重跑 install_all.sh 或手动用 modelscope/hf download 下载"
fi
[[ -n "${DASHSCOPE_API_KEY}" ]] && echo "✅ DASHSCOPE_API_KEY 已设置（来自 .env）" || echo "⚠️  DASHSCOPE_API_KEY 未设置（填 .env 后 ./manage-supervisor restart 生效）"

# ============================================================
# 步骤7: 预下载运行时模型（把 faster-whisper-medium、Demucs、pyannote、speechbrain、resemblyzer 等拉到本地 cache）
# ============================================================
echo ""
echo "=========================================="
echo "📦 步骤 7/8: 预下载运行时模型（推荐，首次翻译不用等）"
echo "=========================================="
PRELOAD_SUCCESS=0
if [ -x "${PROJECT_ROOT}/scripts/preload_models.sh" ]; then
    cd "${PROJECT_ROOT}"
    echo "执行 ./scripts/preload_models.sh（预计 5~15 分钟，失败不影响后续流程，首次翻译会再自动下载）..."
    set +e
    bash "${PROJECT_ROOT}/scripts/preload_models.sh"
    PRELOAD_RC=$?
    set -e
    if [ ${PRELOAD_RC} -eq 0 ]; then
        PRELOAD_SUCCESS=1
        echo "✅ 模型预加载完成"
    else
        echo "⚠️  模型预加载返回码 ${PRELOAD_RC}，跳过（首次翻译时会再自动联网下载）"
    fi
else
    echo "ℹ️  未找到 preload_models.sh，跳过"
fi

# ============================================================
# 步骤7B/8: 离线模型可用性校验（HF_HUB_OFFLINE=1，不加载真权重，只到 cfg 加载 / backend 选择阶段，
#          5s 内出结果，确保 step4 faster-whisper 和 step7 IndexTTS2 config.yaml 真的在本地）
# ============================================================
echo ""
echo "=========================================="
echo "🔍 步骤 7B/8: 离线模型校验（确保翻译前本地 cache 齐全）"
echo "=========================================="
OFFLINE_VERIFY_RC=0
OFFLINE_VERIFY_SKIP=0
if [ -x "${PROJECT_ROOT}/scripts/verify_offline_cache.sh" ] && [ -x "${PROJECT_ROOT}/index-tts/.venv/bin/python" ]; then
    set +e
    bash "${PROJECT_ROOT}/scripts/verify_offline_cache.sh"
    OFFLINE_VERIFY_RC=$?
    set -e
    if [ ${OFFLINE_VERIFY_RC} -eq 0 ]; then
        echo "✅ 离线校验通过（step4 faster-whisper cache / step7 IndexTTS2 config.yaml 均齐全）"
    else
        echo "⚠️  离线校验未通过（退出码 ${OFFLINE_VERIFY_RC}）。可按脚本提示的手动命令修复后，重跑："
        echo "     bash ${PROJECT_ROOT}/scripts/verify_offline_cache.sh"
        echo "   不强制退出；启动服务后首次翻译会再自动尝试下载，但耗时会更长、偶发超时失败。"
    fi
else
    OFFLINE_VERIFY_SKIP=1
    echo "ℹ️  跳过离线校验（脚本/虚拟环境未就绪）"
fi

# ============================================================
# 步骤8: 自动启动服务
# ============================================================
echo ""
echo "=========================================="
echo "🚀 步骤 8/8: 自动启动服务"
echo "=========================================="

AUTO_START_SUCCESS=0
if [ -x "${PROJECT_ROOT}/manage-supervisor.sh" ]; then
    cd "${PROJECT_ROOT}"
    if ./manage-supervisor.sh status &>/dev/null; then
        echo "ℹ️  supervisord 已在运行，执行 restart 以加载最新配置"
        ./manage-supervisor.sh restart || AUTO_START_SUCCESS=0
    else
        echo "执行 ./manage-supervisor.sh start ..."
        ./manage-supervisor.sh start || AUTO_START_SUCCESS=0
    fi

    echo ""
    echo "⏳ 等待服务启动（前端需编译，后端需加载模型，最长 120s）..."
    MAX_WAIT=120
    WAITED=0
    BACKEND_OK=0
    FRONTEND_OK=0
    while [ $WAITED -lt $MAX_WAIT ]; do
        if [ $BACKEND_OK -eq 0 ] && command -v curl &>/dev/null; then
            if curl -sSf --max-time 3 http://127.0.0.1:8000/docs &>/dev/null; then
                BACKEND_OK=1
                echo "✅ 后端 API 已就绪 (http://127.0.0.1:8000/docs)"
            fi
        fi
        if [ $FRONTEND_OK -eq 0 ] && command -v curl &>/dev/null; then
            if curl -sSf --max-time 3 http://127.0.0.1:5173/ &>/dev/null; then
                FRONTEND_OK=1
                echo "✅ 前端 UI 已就绪 (http://127.0.0.1:5173)"
            fi
        fi
        if [ $BACKEND_OK -eq 1 ] && [ $FRONTEND_OK -eq 1 ]; then
            AUTO_START_SUCCESS=1
            break
        fi
        sleep 5
        WAITED=$((WAITED + 5))
        printf "."
    done
    [ $WAITED -gt 0 ] && echo ""

    echo ""
    echo "📊 服务状态："
    cd "${PROJECT_ROOT}" && ./manage-supervisor.sh status || true

    if [ $BACKEND_OK -eq 0 ]; then
        echo "⚠️  后端 API 仍未就绪（首次加载模型较慢），可稍后用 ./manage-supervisor.sh status 查看"
        echo "   后端日志：./manage-supervisor.sh logs-backend"
    fi
    if [ $FRONTEND_OK -eq 0 ]; then
        echo "⚠️  前端 UI 仍未就绪，可稍后访问 http://127.0.0.1:5173 查看"
        echo "   前端日志：./manage-supervisor.sh logs-frontend"
    fi
else
    echo "⚠️  manage-supervisor.sh 不存在或不可执行，跳过自动启动"
fi

# 收集用于展示的 IP 信息（尽力而为，失败不影响）
PUBLIC_IP=""
PRIVATE_IP=""
if command -v curl &>/dev/null; then
    PUBLIC_IP=$(curl -s --max-time 3 ifconfig.me 2>/dev/null || curl -s --max-time 3 ipinfo.io/ip 2>/dev/null || echo "")
fi
PRIVATE_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "")

echo ""
echo "=========================================="
echo "🎉 全部完成"
echo "=========================================="
echo "  镜像组        : ${MIRROR_MODE}"
echo "  HF_ENDPOINT   : ${HF_ENDPOINT:-（直连官方 https://huggingface.co）}"
echo "  PyPI index    : ${UV_DEFAULT_INDEX}"
echo "  NPM registry  : ${NPM_REGISTRY}"
if [ "${PRELOAD_SUCCESS:-0}" -eq 1 ]; then
    echo "  模型预加载    : ✅ 运行时模型已预下载到本地 cache"
else
    echo "  模型预加载    : ⚠️  未完成；首次翻译时会自动联网下载（约 3~8GB）"
fi
if [ "${OFFLINE_VERIFY_SKIP:-0}" -eq 1 ]; then
    echo "  离线模型校验  : ℹ️  跳过（虚拟环境/脚本未就绪）"
elif [ "${OFFLINE_VERIFY_RC:-0}" -eq 0 ]; then
    echo "  离线模型校验  : ✅ step4/step7 本地 cache 齐全（翻译首次启动不会再访问 Hub）"
else
    echo "  离线模型校验  : ⚠️  未通过。重跑校验：bash ./scripts/verify_offline_cache.sh"
fi
if [ $AUTO_START_SUCCESS -eq 1 ]; then
    echo "  服务状态      : ✅ 已自动启动"
else
    echo "  服务状态      : ⚠️  需手动检查状态 (./manage-supervisor.sh status)"
fi
echo ""
echo "📡 访问地址："
echo "  内网/本机 : 前端 http://127.0.0.1:5173"
echo "              API  http://127.0.0.1:8000/docs"
[ -n "${PRIVATE_IP}" ] && echo "  局域网    : 前端 http://${PRIVATE_IP}:5173"
[ -n "${PRIVATE_IP}" ] && echo "              API  http://${PRIVATE_IP}:8000/docs"
[ -n "${PUBLIC_IP}" ]  && echo "  公网(※)  : 前端 http://${PUBLIC_IP}:5173"
[ -n "${PUBLIC_IP}" ]  && echo "              API  http://${PUBLIC_IP}:8000/docs"
[ -n "${PUBLIC_IP}" ]  && echo "  ※ 公网访问需在云控制台放行 5173/8000 TCP 端口（安全组/防火墙）"
echo ""
echo "服务管理命令："
echo "  查看状态       : ./manage-supervisor.sh status"
echo "  重启所有服务   : ./manage-supervisor.sh restart"
echo "  停止所有服务   : ./manage-supervisor.sh stop"
echo "  后端日志       : ./manage-supervisor.sh logs-backend"
echo "  前端日志       : ./manage-supervisor.sh logs-frontend"
echo "修改 .env 后生效: ./manage-supervisor.sh restart"
echo ""
echo "离线模型校验（确保翻译前 cache 齐全）:"
echo "  手动重跑       : bash ./scripts/verify_offline_cache.sh"
echo "命令行使用       : ./run_cli.sh input.mp4"
