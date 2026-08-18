#!/bin/bash

# 模型预加载脚本 - 用于批量处理前的模型预加载
set -e
set -o pipefail

echo "🚀 开始预加载所有模型..."

# 1) 路径 + 加载 .env (通过 setup_env.sh)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/setup_env.sh
source "${PROJECT_ROOT}/scripts/setup_env.sh"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

# 激活 IndexTTS2 虚拟环境
if [ ! -d "${INDEX_TTS_DIR}/.venv" ]; then
    echo "❌ 虚拟环境不存在，请先运行 ./install_all.sh"
    exit 1
fi

cd "${INDEX_TTS_DIR}"
source .venv/bin/activate
cd "${PROJECT_ROOT}"

# 检查 python-dotenv
if ! python -c "import dotenv" 2>/dev/null; then
    echo "📦 安装 python-dotenv..."
    pip install -q "python-dotenv>=1.0.0"
fi

# 报告环境状态
if [ -z "${DASHSCOPE_API_KEY:-}" ]; then
    echo "⚠️  DASHSCOPE_API_KEY 未设置（翻译功能需要）"
fi
echo "   HF_ENDPOINT=${HF_ENDPOINT}"

# 执行模型预加载（用 python -c 直接 PROJECT_ROOT 注入）
python -c "
import sys, os
# 先加载 .env
try:
    from src.dotenv_loader import load_project_env
    load_project_env()
except Exception:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
sys.path.append('${PROJECT_ROOT}')
sys.path.append('${PROJECT_ROOT}/src')
from src.model_preloader import ModelPreloader
print('🔍 初始化模型预加载器...')
preloader = ModelPreloader('config.yaml')
print('🚀 开始预加载所有模型...')
success = preloader.preload_all_models(async_loading=False)
if success:
    print('✅ 所有模型预加载完成！')
    os.environ['VOICE_CLONE_PRELOADER_AVAILABLE'] = 'true'
    with open('/tmp/voice_clone_preloader_available', 'w') as f:
        f.write('true')
    statuses = preloader.get_model_statuses()
    print('\n📊 模型加载状态:')
    for model_name, status_info in statuses.items():
        status = status_info.get('status', '未知')
        print(f'   - {model_name}: {status}')
    print('\n💡 提示: 模型已预加载，后续使用 ./run_cli.sh 执行翻译任务将自动使用预加载的模型')
    sys.exit(0)
else:
    failed_models = preloader.get_failed_models()
    print(f'⚠️  部分模型预加载失败: {failed_models}')
    print('   系统仍可运行，但首次翻译时会重新加载模型')
    sys.exit(1)
"
