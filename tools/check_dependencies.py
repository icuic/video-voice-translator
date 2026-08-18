#!/usr/bin/env python3
"""
依赖检查脚本
验证主项目所需的所有依赖是否已正确安装
"""

import sys
import importlib
from pathlib import Path

# 必需依赖列表（主项目额外依赖）
REQUIRED_DEPENDENCIES = {
    "scipy": "scipy",
    "whisper": "openai-whisper",
    "pyannote": "pyannote.audio",
    "speechbrain": "speechbrain",
    "httpx": "httpx",
    "pydub": "pydub",
    "tiktoken": "tiktoken",
    "demucs": "demucs",  # 音频分离模型（人声和背景音乐分离）
    "resampy": "resampy",  # 音频重采样库（librosa 等库的依赖）
}

# index-tts 核心依赖（应该已安装）
INDEX_TTS_DEPENDENCIES = {
    "torch": "torch",
    "transformers": "transformers",
    "librosa": "librosa",
    "numpy": "numpy",
    "indextts": "indextts",  # index-tts 包本身
}


def check_dependency(module_name: str, package_name: str = None) -> tuple[bool, str]:
    """
    检查依赖是否已安装
    
    Args:
        module_name: Python 模块名（用于 import）
        package_name: PyPI 包名（用于显示）
    
    Returns:
        (是否安装, 错误信息)
    """
    try:
        importlib.import_module(module_name)
        return True, ""
    except ImportError as e:
        pkg_name = package_name or module_name
        return False, f"{pkg_name}: {str(e)}"


def check_all_dependencies():
    """检查所有依赖"""
    print("🔍 检查依赖安装状态...\n")
    
    # 检查 index-tts 核心依赖
    print("📦 index-tts 核心依赖:")
    index_tts_missing = []
    for module, package in INDEX_TTS_DEPENDENCIES.items():
        installed, error = check_dependency(module, package)
        status = "✅" if installed else "❌"
        print(f"  {status} {package}")
        if not installed:
            index_tts_missing.append((package, error))
    
    print("\n📦 主项目额外依赖:")
    project_missing = []
    for module, package in REQUIRED_DEPENDENCIES.items():
        installed, error = check_dependency(module, package)
        status = "✅" if installed else "❌"
        print(f"  {status} {package}")
        if not installed:
            project_missing.append((package, error))
    
    # 总结
    print("\n" + "="*50)
    all_ok = len(index_tts_missing) == 0 and len(project_missing) == 0
    
    if all_ok:
        print("✅ 所有依赖已正确安装！")
        return 0
    else:
        print("❌ 以下依赖缺失或无法导入:\n")
        
        if index_tts_missing:
            print("index-tts 核心依赖:")
            for pkg, error in index_tts_missing:
                print(f"  - {pkg}")
                print(f"    安装命令: cd index-tts && uv sync")
        
        if project_missing:
            print("\n主项目额外依赖:")
            for pkg, error in project_missing:
                print(f"  - {pkg}")
            
            print(f"\n安装命令: uv pip install -r requirements_project.txt")
            print("或使用便捷脚本: ./scripts/install/install_with_uv.sh")
        
        return 1


def main():
    """主函数"""
    # 检查是否在虚拟环境中
    venv_path = Path(sys.executable).parent.parent
    if '.venv' in str(venv_path):
        print(f"✅ 当前虚拟环境: {sys.executable}")
    else:
        print("⚠️  警告: 未检测到虚拟环境")
        print(f"   当前 Python: {sys.executable}")
        print("   建议激活 index-tts/.venv 虚拟环境后再运行此脚本\n")
    
    exit_code = check_all_dependencies()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

