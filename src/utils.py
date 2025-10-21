"""
工具函数模块
提供文件验证、路径处理、日志配置等通用功能
"""

import os
import logging
import yaml
from pathlib import Path
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
        return config
    except FileNotFoundError:
        logging.warning(f"配置文件 {config_path} 未找到，使用默认配置")
        return get_default_config()
    except yaml.YAMLError as e:
        logging.error(f"配置文件解析错误: {e}")
        return get_default_config()


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
            "temp_dir": "./temp"
        },
        "defaults": {
            "language": "en",
            "output_dir": "./output"
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
    
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("video_processor.log", encoding='utf-8')
        ]
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



