#!/bin/bash

# 模型预加载脚本 - 用于批量处理前的模型预加载

echo "🚀 开始预加载所有模型..."

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INDEX_TTS_DIR="${PROJECT_ROOT}/index-tts"

# 激活 IndexTTS2 虚拟环境
if [ ! -d "${INDEX_TTS_DIR}/.venv" ]; then
    echo "❌ 虚拟环境不存在，请先安装 index-tts 依赖"
    echo "   运行: cd index-tts && uv sync --extra webui"
    exit 1
fi

cd "${INDEX_TTS_DIR}"
source .venv/bin/activate

# 设置环境变量
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HOME="${INDEX_TTS_DIR}/.cache/hf"
export PYTHONUNBUFFERED=1

# CUDA/CuDNN 运行时库路径
export LD_LIBRARY_PATH="${INDEX_TTS_DIR}/.venv/lib/python3.10/site-packages/nvidia/cudnn/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"
export PATH="/usr/local/cuda/bin:${PATH}"

# 返回项目目录
cd "${PROJECT_ROOT}"

# 执行模型预加载
python -c "
import sys
import os
sys.path.append('${PROJECT_ROOT}')
sys.path.append('${PROJECT_ROOT}/src')

from src.model_preloader import ModelPreloader

print('🔍 初始化模型预加载器...')
preloader = ModelPreloader('config.yaml')

print('🚀 开始预加载所有模型...')
success = preloader.preload_all_models(async_loading=False)

if success:
    print('✅ 所有模型预加载完成！')
    # 标记预加载状态
    os.environ['VOICE_CLONE_PRELOADER_AVAILABLE'] = 'true'
    with open('/tmp/voice_clone_preloader_available', 'w') as f:
        f.write('true')
    
    # 显示模型状态
    statuses = preloader.get_model_statuses()
    print('\\n📊 模型加载状态:')
    for model_name, status_info in statuses.items():
        status = status_info.get('status', '未知')
        print(f'   - {model_name}: {status}')
    
    print('\\n💡 提示: 模型已预加载，后续使用 run_cli.sh 执行翻译任务将自动使用预加载的模型')
    print('   如果需要重新加载模型，请删除 /tmp/voice_clone_preloader_available 文件')
    sys.exit(0)
else:
    failed_models = preloader.get_failed_models()
    print(f'⚠️  部分模型预加载失败: {failed_models}')
    print('   系统仍可运行，但首次翻译时会重新加载模型')
    sys.exit(1)
"

