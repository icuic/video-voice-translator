"""
步骤2: 音频分离
从音频中分离人声和背景音乐
"""

import os
import json
import numpy as np
from typing import Dict, Any
from ..output_manager import OutputManager, StepNumbers
from .base_step import BaseStep
from .processing_context import ProcessingContext


def convert_to_json_serializable(obj):
    """将numpy类型转换为Python原生类型，以便JSON序列化"""
    if isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_to_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_json_serializable(item) for item in obj]
    else:
        return obj


class Step2AudioSeparation(BaseStep):
    """步骤2: 音频分离"""
    
    def execute(self) -> Dict[str, Any]:
        """执行步骤2: 音频分离"""
        
        # 读取输入音频文件
        audio_path = self.output_manager.get_file_path(StepNumbers.STEP_1, "audio")
        if not os.path.exists(audio_path):
            return {
                "success": False,
                "error": f"输入音频文件不存在: {audio_path}"
            }
        
        # 获取预加载的模型或创建新实例
        audio_separator = self.get_model("AudioSeparator")
        if audio_separator is None:
            from ..audio_separator import AudioSeparator
            audio_separator = AudioSeparator(self.config)
        
        # 分离音频
        vocals_path = self.output_manager.get_file_path(StepNumbers.STEP_2, 'vocals')
        accompaniment_path = self.output_manager.get_file_path(StepNumbers.STEP_2, 'accompaniment')
        
        separation_result = audio_separator.separate_audio_with_paths(
            audio_path, vocals_path, accompaniment_path
        )
        
        if not separation_result.get("success"):
            return {
                "success": False,
                "error": separation_result.get("error", "音频分离失败")
            }
        
        # 保存分离结果元数据
        result_metadata = {
            "success": separation_result.get("success", False),
            "has_background_music": separation_result.get("has_background_music", False),
            "vocals_path": vocals_path,
            "accompaniment_path": accompaniment_path if separation_result.get("has_background_music") else None,
            "separation_quality": separation_result.get("separation_quality", {})
        }
        
        # 转换numpy类型为Python原生类型，以便JSON序列化
        result_metadata = convert_to_json_serializable(result_metadata)
        
        metadata_file = os.path.join(self.task_dir, "02_separation_result.json")
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(result_metadata, f, ensure_ascii=False, indent=2)
        
        self.output_manager.log(f"步骤2完成: 人声已保存到 {vocals_path}")
        if separation_result.get("has_background_music"):
            self.output_manager.log(f"步骤2完成: 背景音乐已保存到 {accompaniment_path}")
        
        return {
            "success": True,
            "vocals_path": vocals_path,
            "accompaniment_path": accompaniment_path if separation_result.get("has_background_music") else None,
            "has_background_music": separation_result.get("has_background_music", False),
            "metadata_file": metadata_file
        }

