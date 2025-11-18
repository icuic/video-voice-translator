"""
工具函数模块
提供文件验证、路径处理、日志配置等通用功能
"""

import os
import logging
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 验证配置
        validate_config(config)
        return config
    except FileNotFoundError:
        logging.warning(f"配置文件 {config_path} 未找到，使用默认配置")
        return get_default_config()
    except yaml.YAMLError as e:
        logging.error(f"配置文件解析错误: {e}")
        return get_default_config()


def validate_config(config: Dict[str, Any]) -> None:
    """
    验证配置文件的完整性和正确性
    
    Args:
        config: 配置字典
        
    Raises:
        ValueError: 配置验证失败
    """
    required_sections = [
        'audio', 'video', 'whisper', 'translation', 'voice_cloning'
    ]
    
    for section in required_sections:
        if section not in config:
            logging.warning(f"配置缺少必要部分: {section}")
    
    # 验证Whisper配置
    if 'whisper' in config:
        whisper_config = config['whisper']
        if 'model_size' not in whisper_config:
            logging.warning("Whisper配置缺少model_size")
        if 'device' not in whisper_config:
            logging.warning("Whisper配置缺少device")
    
    # 验证翻译配置
    if 'translation' in config:
        translation_config = config['translation']
        if 'source_language' not in translation_config:
            logging.warning("翻译配置缺少source_language")
        if 'target_language' not in translation_config:
            logging.warning("翻译配置缺少target_language")
        if 'model' not in translation_config:
            logging.warning("翻译配置缺少model")
    
    # 验证音色克隆配置
    if 'voice_cloning' in config:
        voice_config = config['voice_cloning']
        if 'model_path' not in voice_config:
            logging.warning("音色克隆配置缺少model_path")
        # 注意：device 配置已移除，IndexTTS2 会自动检测并使用可用的设备（CUDA/CPU）
        # 因此不再检查 device 配置项
    
    logging.info("配置验证完成")


def get_default_config() -> Dict[str, Any]:
    """
    获取默认配置
    
    Returns:
        默认配置字典
    """
    return {
        "audio": {
            "sample_rate": 16000,
            "format": "wav",
            "channels": 1,
            "bit_depth": 16
        },
        "video": {
            "supported_formats": ["mp4", "avi", "mov", "mkv", "mp3", "wav"],
            "temp_dir": "./data/temp"
        },
        "defaults": {
            "language": "en",
            "output_dir": "./data/outputs"
        },
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        }
    }


def setup_logging(config: Dict[str, Any]) -> None:
    """
    设置日志配置
    
    Args:
        config: 配置字典
    """
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper())
    format_str = log_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    enable_file = log_config.get("enable_file", True)
    
    # 使用配置中的日志目录
    log_dir = log_config.get("log_dir", "./data/logs")
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    
    # 生成带时间戳的日志文件名
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = log_dir_path / f"media_processor_{timestamp}.log"
    
    handlers = [logging.StreamHandler()]
    
    # 仅当启用文件日志且日志目录存在时，才添加文件处理器
    if enable_file and log_dir_path.exists():
        handlers.append(logging.FileHandler(str(log_file), encoding='utf-8'))
    
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=handlers
    )


def validate_file_path(file_path: str) -> bool:
    """
    验证文件路径是否存在
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件是否存在
    """
    return os.path.isfile(file_path)


def cleanup_temp_files(temp_dir: str = "./data/temp", max_age_hours: int = 24) -> None:
    """
    清理临时文件
    
    Args:
        temp_dir: 临时文件目录
        max_age_hours: 文件最大保留时间（小时）
    """
    import time
    import glob
    
    if not os.path.exists(temp_dir):
        return
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    # 清理超过指定时间的文件
    for file_path in glob.glob(os.path.join(temp_dir, "*")):
        if os.path.isfile(file_path):
            file_age = current_time - os.path.getmtime(file_path)
            if file_age > max_age_seconds:
                try:
                    os.remove(file_path)
                    logging.info(f"清理临时文件: {file_path}")
                except Exception as e:
                    logging.warning(f"清理临时文件失败: {file_path}, 错误: {e}")
    
    logging.info(f"临时文件清理完成: {temp_dir}")


def cleanup_on_exit(temp_files: list) -> None:
    """
    程序退出时清理临时文件
    
    Args:
        temp_files: 需要清理的临时文件列表
    """
    import atexit
    
    def cleanup():
        for file_path in temp_files:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logging.info(f"退出时清理临时文件: {file_path}")
                except Exception as e:
                    logging.warning(f"清理临时文件失败: {file_path}, 错误: {e}")
    
    atexit.register(cleanup)


def validate_file_format(file_path: str, supported_formats: list) -> bool:
    """
    验证文件格式是否支持
    
    Args:
        file_path: 文件路径
        supported_formats: 支持的格式列表
        
    Returns:
        格式是否支持
    """
    file_ext = Path(file_path).suffix.lower().lstrip('.')
    return file_ext in supported_formats


def create_output_dir(output_dir: str) -> None:
    """
    创建输出目录
    
    Args:
        output_dir: 输出目录路径
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)


def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    获取文件基本信息
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件信息字典
    """
    path_obj = Path(file_path)
    stat = path_obj.stat()
    
    return {
        "name": path_obj.name,
        "size": stat.st_size,
        "extension": path_obj.suffix.lower().lstrip('.'),
        "modified_time": stat.st_mtime
    }


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小显示
    
    Args:
        size_bytes: 文件大小（字节）
        
    Returns:
        格式化后的文件大小字符串
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def safe_filename(filename: str) -> str:
    """
    生成安全的文件名（移除特殊字符）
    
    Args:
        filename: 原始文件名
        
    Returns:
        安全的文件名
    """
    import re
    # 移除或替换特殊字符
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return safe_name


def detect_language(input_path: str) -> str:
    """检测输入文件的语言"""
    try:
        import whisper
        
        # 如果是视频文件，先提取音频
        file_ext = os.path.splitext(input_path)[1].lower()
        if file_ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']:
            # 提取音频进行语言检测
            from src.media_processor import MediaProcessor
            temp_config = load_config()
            media_processor = MediaProcessor(temp_config)
            result = media_processor.process(input_path, 'output')
            audio_path = result['audio_path']  # 从结果中获取音频路径
        else:
            audio_path = input_path
        
        # 使用Whisper检测语言
        model = whisper.load_model("base")
        audio = whisper.load_audio(audio_path)
        audio = whisper.pad_or_trim(audio)
        
        # 检测语言
        mel = whisper.log_mel_spectrogram(audio).to(model.device)
        _, probs = model.detect_language(mel)
        
        # 获取最可能的语言
        detected_language = max(probs, key=probs.get)
        
        # 清理临时文件
        if file_ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv'] and os.path.exists(audio_path):
            os.remove(audio_path)
        
        return detected_language
        
    except Exception as e:
        logging.warning(f'语言检测失败: {e}，使用默认语言 en')
        return 'en'


def apply_language_settings(config: dict, source_lang: str, target_lang: str, voice_model: str) -> dict:
    """应用语言设置到配置"""
    
    # 语言名称到代码的映射
    language_mapping = {
        "中文": "zh",
        "English": "en"
    }
    
    # 将显示名称转换为语言代码
    source_code = language_mapping.get(source_lang, source_lang)
    target_code = language_mapping.get(target_lang, target_lang)
    
    # 翻译提示词
    translation_prompts = {
        # 中文相关
        ('zh', 'en'): "将以下中文文本翻译成英文，使用自然流畅的英文表达",
        ('zh', 'zh'): "将以下中文文本翻译成中文，使用自然流畅的中文表达",
        
        # 英文相关
        ('en', 'zh'): "将以下英文文本翻译成中文，使用自然流畅的中文表达",
        ('en', 'en'): "将以下英文文本翻译成英文，使用自然流畅的英文表达",
    }
    
    # 语音识别语言设置
    whisper_languages = {
        'zh': 'zh',
        'en': 'en'
    }
    
    # 音色克隆目标语言
    voice_languages = {
        'zh': 'zh',
        'en': 'en'
    }
    
    # 应用翻译设置
    if 'translation' not in config:
        config['translation'] = {}
    
    config['translation']['source_language'] = source_code
    config['translation']['target_language'] = target_code
    config['translation']['prompt'] = translation_prompts.get(
        (source_code, target_code), 
        f"将{source_lang}文本翻译成{target_lang}，保持原意和语调"
    )
    
    # 应用Whisper设置
    if 'whisper' not in config:
        config['whisper'] = {}
    
    config['whisper']['language'] = whisper_languages.get(source_code, 'auto')
    
    # 应用音色克隆设置
    if 'voice_cloning' not in config:
        config['voice_cloning'] = {}
    
    config['voice_cloning']['target_language'] = voice_languages.get(target_code, 'en')
    config['voice_cloning']['model'] = voice_model
    
    return config



