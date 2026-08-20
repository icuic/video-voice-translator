#!/bin/bash
# 模型/配置 离线可用性校验脚本（设计给 install_all.sh 步骤7之后调用，或用户手动重跑校验）
# 目标：用 HF_HUB_OFFLINE=1 强制不走任何网络，只靠本地 cache，验证：
#   1. step4（语音识别）WhisperProcessor 能初始化到 faster-whisper backend（证明 Systran/faster-whisper-medium 真的在本地）
#   2. step7（音色克隆）VoiceCloner 能走到 IndexTTS2 构造前，checkpoints/config.yaml 真的存在且可 parse
# 不真的加载 10GB 权重，只到 cfg 加载 / backend 选择阶段，一般 5s 内出结果。

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

cd "${PROJECT_ROOT}"

# shellcheck source=scripts/setup_env.sh
if [ -f "${PROJECT_ROOT}/scripts/setup_env.sh" ]; then
    source "${PROJECT_ROOT}/scripts/setup_env.sh"
fi

echo ""
echo "=========================================="
echo "🔍 离线模型可用性校验（HF_HUB_OFFLINE=1）"
echo "=========================================="
echo "   PROJECT_ROOT = ${PROJECT_ROOT}"

if [ ! -f "${INDEX_TTS_DIR}/.venv/bin/python" ]; then
    echo "❌ index-tts/.venv 不存在（先执行 ./install_all.sh）"
    exit 2
fi

export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
"${INDEX_TTS_DIR}/.venv/bin/python" - "${PROJECT_ROOT}" <<'PYEOF'
import sys, os, logging, types, traceback
logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s: %(message)s")
PROJECT_ROOT = sys.argv[1]
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "index-tts"))

from src.dotenv_loader import load_project_env
try:
    load_project_env()
except Exception:
    pass

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
print(f"   HF_HUB_OFFLINE       = {os.environ['HF_HUB_OFFLINE']}")
print(f"   TRANSFORMERS_OFFLINE = {os.environ['TRANSFORMERS_OFFLINE']}")
print(f"   HF_ENDPOINT          = {os.environ.get('HF_ENDPOINT','（直连官方）')}")
print("")

errors = []

# -------- 检查 1: step4 WhisperProcessor（本地 whisper cache 可用即可，faster-whisper 或 whisper 都通过；
#          两者都不存在才报错 —— 因为 whisper_processor.py 已经有 faster→whisper 自动降级逻辑） --------
try:
    from src.utils import load_config
    from src.whisper_processor import WhisperProcessor
    cfg = load_config(os.path.join(PROJECT_ROOT, "config.yaml"))
    wp = WhisperProcessor(cfg)
    backend = getattr(wp, "backend", "unknown")
    if backend in ("faster-whisper", "whisper"):
        print(f"✅ [step4] WhisperProcessor 本地可用（backend={backend}）")
    else:
        errors.append(
            f"[step4] WhisperProcessor backend={backend}，预期 faster-whisper 或 whisper。"
            f"请运行：HF_ENDPOINT={os.environ.get('HF_ENDPOINT','https://hf-mirror.com')} "
            f"bash {PROJECT_ROOT}/scripts/preload_models.sh"
        )
except Exception as e:
    errors.append(
        f"[step4] 初始化失败 {type(e).__name__}: {e}。"
        f"通常是 faster-whisper-medium / openai-whisper medium 未下载到本地 cache。"
        f"请手动预下载：HF_ENDPOINT=https://hf-mirror.com bash {PROJECT_ROOT}/scripts/preload_models.sh"
    )

# -------- 检查 2: step7 VoiceCloner → IndexTTS2（checkpoints/config.yaml） --------
try:
    import indextts.infer_v2 as M

    def fake_init(self, cfg_path, model_dir, **kw):
        import os as _os
        from omegaconf import OmegaConf as _OC
        if not _os.path.isfile(cfg_path):
            raise FileNotFoundError(f"OFFLINE FAIL: cfg_path 不存在: {cfg_path}")
        self.cfg = _OC.load(cfg_path)
        if not hasattr(self.cfg, "gpt") or not hasattr(self.cfg.gpt, "stop_mel_token"):
            raise ValueError(f"OFFLINE FAIL: config.yaml 非法，缺少 gpt.stop_mel_token。文件: {cfg_path}")
        self.model_dir = model_dir
    M.IndexTTS2.__init__ = fake_init

    from src.voice_cloner import VoiceCloner
    from src.utils import load_config as _lc
    cfg2 = _lc(os.path.join(PROJECT_ROOT, "config.yaml"))
    vc = VoiceCloner(cfg2)
    expected_cfg = os.path.join(getattr(vc, "model_path", ""), "checkpoints/config.yaml")
    if not os.path.isfile(expected_cfg):
        errors.append(
            f"[step7] IndexTTS2 config.yaml 仍然缺失: {expected_cfg}。"
            f"请手动补：curl -sSL -o {expected_cfg} "
            f"https://hf-mirror.com/IndexTeam/IndexTTS-2/resolve/main/config.yaml"
        )
    else:
        print("✅ [step7] IndexTTS2 config.yaml 本地就绪 + 可 OmegaConf.load")
except Exception as e:
    errors.append(
        f"[step7] VoiceCloner/IndexTTS2 配置阶段失败 {type(e).__name__}: {e}。"
        f"通常是 index-tts/checkpoints/config.yaml 未下载。"
        f"请手动补：curl -sSL -o {os.path.join(PROJECT_ROOT,'index-tts/checkpoints/config.yaml')} "
        f"https://hf-mirror.com/IndexTeam/IndexTTS-2/resolve/main/config.yaml"
    )

print("")
if errors:
    print("❌ 离线校验失败：")
    for i, msg in enumerate(errors, 1):
        print(f"   {i}. {msg}")
    print("")
    print("修复后重跑：")
    print(f"  bash {os.path.relpath(os.path.join(PROJECT_ROOT,'scripts/verify_offline_cache.sh'), os.getcwd()) or './scripts/verify_offline_cache.sh'}")
    sys.exit(1)
print("✅ 离线校验通过 ✅ 翻译流水线 step4/step7 cache 全齐，新装机器不用等首次翻译再下载。")
PYEOF
PY_RC=$?

echo ""
if [ ${PY_RC} -eq 0 ]; then
    echo "🎉 verify_offline_cache.sh 通过"
    exit 0
else
    echo "⚠️  verify_offline_cache.sh 退出码=${PY_RC}（翻译会在首次运行时再自动尝试下载，但会很慢）"
    echo "   手动重跑校验命令: bash ${PROJECT_ROOT}/scripts/verify_offline_cache.sh"
    exit ${PY_RC}
fi
