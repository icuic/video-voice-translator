#!/bin/bash
# 安装 IndexTTS2（含 5.5GB 模型下载）
# 环境变量全部继承自父 install.sh / .env：
#   EFFECTIVE_MIRROR / UV_DEFAULT_INDEX / HF_ENDPOINT / UV_HTTP_TIMEOUT / GIT_HTTP_*
# 全程无交互。

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# 优先从 .env 加载（单独跑本脚本的场景）
# shellcheck source=scripts/load_dotenv.sh
source "${PROJECT_ROOT}/scripts/load_dotenv.sh"

# 默认值兜底
EFFECTIVE_MIRROR="${EFFECTIVE_MIRROR:-china}"
UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://mirrors.aliyun.com/pypi/simple}"
if [[ -z "${HF_ENDPOINT}" ]]; then
    if [[ "${EFFECTIVE_MIRROR}" == "official" ]]; then
        HF_ENDPOINT="https://huggingface.co"
    else
        HF_ENDPOINT="https://hf-mirror.com"
    fi
fi
export HF_ENDPOINT
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-120}"
export GIT_HTTP_LOW_SPEED_LIMIT="${GIT_HTTP_LOW_SPEED_LIMIT:-1000}"
export GIT_HTTP_LOW_SPEED_TIME="${GIT_HTTP_LOW_SPEED_TIME:-30}"

echo "=========================================="
echo "IndexTTS2 安装脚本"
echo "  镜像组       : ${EFFECTIVE_MIRROR}"
echo "  PyPI index   : ${UV_DEFAULT_INDEX}"
echo "  HF_ENDPOINT  : ${HF_ENDPOINT}"
echo "=========================================="

# 0. 检查 uv
if ! command -v uv &>/dev/null; then
    echo "📦 安装 uv..."
    if command -v pip &>/dev/null; then
        pip install -U uv
    elif command -v pip3 &>/dev/null; then
        pip3 install -U uv
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi
echo "✅ uv: $(uv --version 2>/dev/null | head -1 || echo OK)"

# 1. 克隆仓库（如缺或空）
if [ ! -d "${PROJECT_ROOT}/index-tts" ] || [ ! -f "${PROJECT_ROOT}/index-tts/pyproject.toml" ]; then
    if [ -d "${PROJECT_ROOT}/index-tts" ]; then rm -rf "${PROJECT_ROOT}/index-tts"; fi
    echo "📥 克隆 index-tts 仓库..."
    git clone https://github.com/index-tts/index-tts.git "${PROJECT_ROOT}/index-tts"
fi
echo "✅ index-tts 仓库就绪"

cd "${PROJECT_ROOT}/index-tts"

# 锁定 commit
PINNED="c7d3cff0ff8402c1d8e94b9848305d47e39f981c"
echo "🔒 切换到 commit ${PINNED}"
git checkout "${PINNED}"
echo "✅ HEAD -> $(git rev-parse --short HEAD)"

[ -f pyproject.toml ] || { echo "❌ pyproject.toml 缺失，克隆失败？"; exit 1; }

# 2. 跳过 git-lfs 示例音频（非必需，用于官方 demo；本项目用户上传自己的音视频，不需要 index-tts 仓库里的 LFS 示例音频）
#    这样新装机器不需要额外安装 git-lfs / 不需要下载几百 MB 的示例音频 LFS 文件，节省时间和流量。
if command -v git-lfs &>/dev/null; then
    echo "ℹ️  本机已有 git-lfs，但跳过 index-tts 仓库 LFS 示例音频（本项目不需要）"
    git -C "${PROJECT_ROOT}/index-tts" lfs install --local 2>/dev/null || true
else
    echo "ℹ️  跳过 git-lfs 安装（index-tts 仓库的 LFS 示例音频本项目不使用）"
fi

# 3. uv sync 安装 Python 依赖
echo "📦 uv sync (index=${UV_DEFAULT_INDEX})"
uv sync --all-extras --default-index "${UV_DEFAULT_INDEX}"
echo "✅ IndexTTS2 依赖安装完成"

# 4. 验证（可选）
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    python -c "from indextts.infer_v2 import IndexTTS2; print('✅ IndexTTS2 import OK')" 2>/dev/null || echo "⚠️  导入验证失败（运行时模型下载完成后通常 OK）"
    deactivate
fi

# 5. 下载模型（~5.5GB），HF_ENDPOINT 全程从 .env / 镜像组取得
echo ""
echo "=========================================="
echo "📥 下载 IndexTTS2 模型文件（必需，~5.5GB）"
echo "   HF_ENDPOINT=${HF_ENDPOINT}"
echo "=========================================="

[ -f ".venv/bin/activate" ] || { echo "❌ 虚拟环境不存在"; exit 1; }
source .venv/bin/activate

if [ -f "checkpoints/gpt.pth" ] && [ -f "checkpoints/s2mel.pth" ]; then
    MODEL_SIZE=$(du -sh checkpoints/ 2>/dev/null | awk '{print $1}' || echo "未知")
    echo "✅ 模型已存在，跳过下载（大小: ${MODEL_SIZE}）"
else
    FAILED=false
    echo "尝试 ModelScope 下载..."
    if ! command -v modelscope &>/dev/null; then
        echo "📦 安装 modelscope..."
        uv tool install modelscope || FAILED=true
    fi
    if [ "${FAILED}" = "false" ] && command -v modelscope &>/dev/null; then
        if ! modelscope download --model IndexTeam/IndexTTS-2 --local_dir checkpoints 2>&1; then
            echo "⚠️  ModelScope 失败，回退 HuggingFace"
            FAILED=true
        fi
    fi
    if [ "${FAILED}" = "true" ] || [ ! -f "checkpoints/gpt.pth" ]; then
        echo "📥 HuggingFace 下载（HF_ENDPOINT=${HF_ENDPOINT}）..."
        if ! command -v hf &>/dev/null; then
            echo "📦 安装 huggingface-hub[cli,hf_xet]..."
            uv tool install "huggingface-hub[cli,hf_xet]" || { echo "❌ huggingface-hub 安装失败"; exit 1; }
        fi
        hf download IndexTeam/IndexTTS-2 --local-dir=checkpoints || { echo "❌ HuggingFace 下载失败"; exit 1; }
    fi
    if [ -f "checkpoints/gpt.pth" ] && [ -f "checkpoints/s2mel.pth" ]; then
        MODEL_SIZE=$(du -sh checkpoints/ 2>/dev/null | awk '{print $1}' || echo "未知")
        echo "✅ 模型下载完成（大小: ${MODEL_SIZE}）"
    else
        echo "❌ 模型下载失败，请手动下载 https://github.com/index-tts/index-tts"
        exit 1
    fi
fi

# 6. 兜底：确保 checkpoints/config.yaml 存在（第三方 ensure_config_available 有时会失败，
#    但 step7 音色克隆 IndexTTS2(infer_v2) 第 82 行硬执行 OmegaConf.load(cfg_path)，
#    缺了就 FileNotFoundError；这里在模型下载完成后直接用 curl 再补一次，彻底避免）
if [ ! -f "checkpoints/config.yaml" ]; then
    echo "⚠️  checkpoints/config.yaml 缺失，直接用 curl 从 IndexTeam/IndexTTS-2 仓库补下载..."
    CFG_CURL_RC=0
    if [ -n "${HF_ENDPOINT}" ]; then
        curl -sSL --max-time 30 -o checkpoints/config.yaml \
            "${HF_ENDPOINT%/}/IndexTeam/IndexTTS-2/resolve/main/config.yaml" || CFG_CURL_RC=$?
    fi
    if [ "${CFG_CURL_RC}" -ne 0 ] || [ ! -f "checkpoints/config.yaml" ]; then
        echo "  ⚠️  HF_ENDPOINT=${HF_ENDPOINT} 下载失败，回退 hf-mirror 直连..."
        CFG_CURL_RC=0
        curl -sSL --max-time 30 -o checkpoints/config.yaml \
            "https://hf-mirror.com/IndexTeam/IndexTTS-2/resolve/main/config.yaml" || CFG_CURL_RC=$?
    fi
    if [ -f "checkpoints/config.yaml" ] && grep -q "^gpt:" checkpoints/config.yaml 2>/dev/null; then
        echo "✅ checkpoints/config.yaml 已补全 ($(wc -c < checkpoints/config.yaml) bytes)"
    else
        echo "❌ checkpoints/config.yaml 仍缺失。请手动执行以下命令补全："
        echo "    cd ${PROJECT_ROOT}/index-tts && \\"
        echo "    curl -sSL -o checkpoints/config.yaml \\"
        echo "      https://hf-mirror.com/IndexTeam/IndexTTS-2/resolve/main/config.yaml"
    fi
fi

deactivate
cd "${PROJECT_ROOT}"
echo ""
echo "=========================================="
echo "✅ IndexTTS2 安装完成"
echo "=========================================="
