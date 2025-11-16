"""
增强的媒体处理器模块
集成音频分离功能的媒体处理器
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from .media_processor import MediaProcessor
from .audio_separator import AudioSeparator
from .audio_merger import AudioMerger
from .output_manager import OutputManager, StepNumbers
from .utils import validate_file_path, create_output_dir, safe_filename


class EnhancedMediaProcessor(MediaProcessor):
    """增强的媒体处理器类，支持音频分离功能"""

    def __init__(self, config_path_or_dict = "config.yaml"):
        super().__init__(config_path_or_dict)
        self.audio_separator = AudioSeparator(self.config)
        self.audio_merger = AudioMerger(self.config)
        self.enable_separation = self.config.get("defaults", {}).get("enable_separation", True)
        self.logger.info("增强媒体处理器初始化完成")

    def process_with_output_manager(self, input_path: str, output_manager: OutputManager,
                                   language: Optional[str] = None,
                                   force_separation: bool = False) -> Dict[str, Any]:
        self.logger.info(f"开始增强处理: {input_path}")

        if not validate_file_path(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        if language is None:
            language = self.default_language

        try:
            self.logger.info("执行基础媒体处理...")
            audio_path = output_manager.get_file_path(StepNumbers.STEP_1, "audio")
            audio_result = self.audio_extractor.extract(input_path, audio_path)
            output_manager.log(f"步骤1完成: 音频已提取到 {audio_path}")

            separation_needed = False
            separation_result = None
            detection_result = {"has_background_music": False}

            if self.enable_separation or force_separation:
                self.logger.info("检测背景音乐...")
                detection_result = self.audio_separator.detect_background_music(audio_path)
                if detection_result["has_background_music"]:
                    self.logger.info("检测到背景音乐，开始分离...")
                    vocals_path = output_manager.get_file_path(StepNumbers.STEP_2, "vocals")
                    accompaniment_path = output_manager.get_file_path(StepNumbers.STEP_2, "accompaniment")
                    separation_result = self.audio_separator.separate_audio_with_paths(
                        audio_path, vocals_path, accompaniment_path
                    )
                    separation_needed = True
                    output_manager.log("步骤2完成: 音频分离完成")
                    output_manager.log(f"  - 人声: {vocals_path}")
                    output_manager.log(f"  - 背景: {accompaniment_path}")
                else:
                    self.logger.info("未检测到背景音乐，跳过分离步骤")
                    output_manager.log("步骤2跳过: 未检测到背景音乐")

            enhanced_result = {
                "success": True,
                "input_path": input_path,
                "task_dir": output_manager.task_dir,
                "language": language,
                "audio_path": audio_path,
                "separation_needed": separation_needed,
                "separation_result": separation_result,
                "processing_info": {
                    "input_size": os.path.getsize(input_path),
                    "output_size": audio_result["output_size"],
                    "separation_enabled": separation_needed,
                    "has_background_music": detection_result["has_background_music"]
                }
            }

            if separation_needed and separation_result:
                enhanced_result.update({
                    "vocals_path": separation_result["vocals_path"],
                    "accompaniment_path": separation_result["accompaniment_path"],
                    "separation_quality": separation_result["separation_quality"]
                })

            output_manager.log("增强处理完成")
            return enhanced_result

        except Exception as e:
            self.logger.error(f"增强处理失败: {e}")
            output_manager.log(f"处理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "input_path": input_path,
                "audio_path": None,
                "separation_needed": False,
                "separation_result": None
            }

