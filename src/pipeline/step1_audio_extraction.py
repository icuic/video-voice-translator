"""
步骤1: 音频提取
从视频/音频文件提取音频，保存原始文件和元数据
"""

import os
import shutil
import json
import librosa
from typing import Dict, Any
from ..output_manager import OutputManager, StepNumbers
from ..utils import validate_file_path
from .base_step import BaseStep
from .processing_context import ProcessingContext


class Step1AudioExtraction(BaseStep):
    """步骤1: 音频提取"""
    
    def execute(self) -> Dict[str, Any]:
        """执行步骤1: 音频提取"""
        
        # 保存原始输入文件
        original_file = self.context.save_original_input()
        self.logger.info(f"原始输入文件已保存: {original_file}")
        
        # 保存任务参数
        params_file = self.context.save_task_params()
        self.logger.info(f"任务参数已保存: {params_file}")
        
        # 获取全局进度回调
        progress_callback = getattr(self.context, 'progress_callback', None)

        # 定义进度回调包装函数
        def extraction_progress_callback(progress: float, message: str):
            """音频提取进度回调包装"""
            if progress_callback:
                # 步骤1的索引为1（如果跳过步骤3则为1，否则为1）
                progress_callback(1, "步骤1: 音频提取", progress, message, 0, 0)

        # 处理视频或音频文件
        if self.context.is_video:
            # 视频文件：使用EnhancedMediaProcessor提取音频
            from ..enhanced_media_processor import EnhancedMediaProcessor
            media_processor = EnhancedMediaProcessor(self.config)
            result = media_processor.process_with_output_manager(
                self.context.input_path,
                self.output_manager,
                progress_callback=extraction_progress_callback
            )

            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "视频处理失败")
                }

            # 保存元数据
            metadata = result.get("metadata", {})
            metadata_file = self.context.save_metadata(metadata)
            self.logger.info(f"元数据已保存: {metadata_file}")

            # 设置视频信息到统计
            if metadata:
                duration = metadata.get("duration", 0)
                resolution = f"{metadata.get('width', 0)}x{metadata.get('height', 0)}"
                fps = metadata.get("fps", 0)
                self.stats.set_video_info(duration, resolution, fps)

            audio_path = result['audio_path']
            
        else:
            # 音频文件：直接复制到任务目录
            # 报告开始进度
            if progress_callback:
                progress_callback(1, "步骤1: 音频提取", 0, "开始音频提取...", 0, 0)

            audio_path = self.output_manager.get_file_path(StepNumbers.STEP_1, "audio")
            shutil.copy2(self.context.input_path, audio_path)

            # 报告进度（复制完成）
            if progress_callback:
                progress_callback(1, "步骤1: 音频提取", 50, "音频文件复制完成", 0, 0)

            # 获取音频文件信息
            try:
                duration = librosa.get_duration(filename=audio_path)
                metadata = {
                    "duration": duration,
                    "is_video": False,
                    "is_audio": True,
                    "sample_rate": 16000
                }
                self.stats.set_video_info(duration, "", 0)
            except Exception as e:
                self.logger.warning(f"无法获取音频时长: {e}")
                metadata = {
                    "duration": 0,
                    "is_video": False,
                    "is_audio": True
                }
                self.stats.set_video_info(0, "", 0)

            # 保存元数据
            metadata_file = self.context.save_metadata(metadata)
            self.logger.info(f"元数据已保存: {metadata_file}")

            # 报告完成进度
            if progress_callback:
                progress_callback(1, "步骤1: 音频提取", 100, "音频提取完成", 0, 0)
        
        self.output_manager.log(f"步骤1完成: 音频已提取到 {audio_path}")
        
        return {
            "success": True,
            "audio_path": audio_path,
            "original_file": original_file,
            "params_file": params_file,
            "metadata_file": metadata_file,
            "metadata": metadata
        }

