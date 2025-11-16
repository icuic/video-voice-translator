"""
媒体处理主模块
整合元数据提取和音频提取功能，提供统一的媒体处理接口
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from .metadata_extractor import MetadataExtractor
from .audio_extractor import AudioExtractor
from .utils import (
    load_config, setup_logging, validate_file_path,
    validate_file_format, create_output_dir, safe_filename
)


class MediaProcessor:
    """媒体处理主类（支持视频/音频）"""

    def __init__(self, config_path_or_dict = "config.yaml"):
        """
        初始化媒体处理器

        Args:
            config_path_or_dict: 配置文件路径（字符串）或配置字典
        """
        if isinstance(config_path_or_dict, dict):
            self.config = config_path_or_dict
            # 验证配置字典
            from .utils import validate_config
            validate_config(self.config)
        else:
            self.config = load_config(config_path_or_dict)
        setup_logging(self.config)
        self.logger = logging.getLogger(__name__)

        self.metadata_extractor = MetadataExtractor()
        self.audio_extractor = AudioExtractor(self.config)

        self.supported_formats = self.config.get("video", {}).get(
            "supported_formats", ["mp4", "avi", "mov", "mkv", "mp3", "wav"]
        )
        self.default_language = self.config.get("defaults", {}).get("language", "en")
        self.default_output_dir = self.config.get("defaults", {}).get("output_dir", "./data/outputs")
        self.temp_dir = self.config.get("video", {}).get("temp_dir", "./data/temp")

        self.logger.info("媒体处理器初始化完成")

        try:
            from .utils import cleanup_temp_files
            cleanup_temp_files(self.temp_dir)
        except Exception as e:
            self.logger.warning(f"临时文件清理失败: {e}")

    def process(self, input_path: str, output_dir: Optional[str] = None,
                language: Optional[str] = None) -> Dict[str, Any]:
        """
        处理媒体文件（视频或音频）
        """
        self.logger.info(f"开始处理文件: {input_path}")

        if not validate_file_path(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        if not validate_file_format(input_path, self.supported_formats):
            raise ValueError(f"不支持的文件格式: {Path(input_path).suffix}")

        if output_dir is None:
            output_dir = self.default_output_dir
        if language is None:
            language = self.default_language

        create_output_dir(output_dir)

        try:
            metadata = self.metadata_extractor.extract(input_path)

            input_name = Path(input_path).stem
            safe_name = safe_filename(input_name)
            audio_output_path = os.path.join(output_dir, f"{safe_name}_audio.wav")

            audio_result = self.audio_extractor.extract(input_path, audio_output_path)

            result = {
                "success": True,
                "input_path": input_path,
                "output_dir": output_dir,
                "audio_path": audio_output_path,
                "metadata": metadata,
                "audio_result": audio_result,
                "language": language,
                "processing_info": {
                    "input_size": metadata["file_info"]["size"],
                    "output_size": audio_result["output_size"],
                    "duration": self._get_duration(metadata),
                    "format": metadata["file_info"]["extension"]
                }
            }

            self.logger.info("文件处理完成")
            return result

        except Exception as e:
            self.logger.error(f"文件处理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "input_path": input_path
            }

    def _get_duration(self, metadata: Dict[str, Any]) -> float:
        if "format" in metadata and "duration" in metadata["format"]:
            return metadata["format"]["duration"]
        if "video" in metadata and "duration" in metadata["video"]:
            return metadata["video"]["duration"]
        if "audio" in metadata and "duration" in metadata["audio"]:
            return metadata["audio"]["duration"]
        return 0.0


