"""
处理上下文类
统一管理任务参数、配置、输出管理器等运行时对象
"""

import os
import json
from typing import Dict, Any, Optional
from pathlib import Path
from ..output_manager import OutputManager
from ..performance_stats import PerformanceStats


class ProcessingContext:
    """处理上下文类 - 统一的数据传递对象"""
    
    def __init__(self, 
                 input_path: str,
                 source_lang: str,
                 target_lang: str,
                 voice_model: str,
                 single_speaker: bool,
                 output_dir: str,
                 config: Dict[str, Any],
                 output_manager: OutputManager,
                 stats: PerformanceStats,
                 pause_after_step4: bool = False,
                 pause_after_step5: bool = False,
                 progress_callback: Optional[callable] = None):
        """
        初始化处理上下文
        
        Args:
            input_path: 输入文件路径
            source_lang: 源语言
            target_lang: 目标语言
            voice_model: 音色克隆模型
            single_speaker: 是否仅一人说话
            output_dir: 输出目录
            config: 配置字典
            output_manager: 输出管理器
            stats: 性能统计
            pause_after_step4: 是否在步骤4后暂停
            pause_after_step5: 是否在步骤5后暂停
        """
        self.input_path = input_path
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.voice_model = voice_model
        self.single_speaker = single_speaker
        self.output_dir = output_dir
        self.config = config
        self.output_manager = output_manager
        self.stats = stats
        self.pause_after_step4 = pause_after_step4
        self.pause_after_step5 = pause_after_step5
        self.progress_callback = progress_callback
        
        # 任务目录
        self.task_dir = output_manager.task_dir
        
        # 文件类型判断
        file_ext = os.path.splitext(input_path)[1].lower()
        self.is_audio = file_ext in ['.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg']
        self.is_video = file_ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']
        
        # 原始视频路径（如果是音频文件则为None）
        self.original_video_path = input_path if self.is_video else None
    
    def save_task_params(self) -> str:
        """
        保存任务参数到任务目录
        
        Returns:
            任务参数文件路径
        """
        params = {
            "input_path": self.input_path,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "voice_model": self.voice_model,
            "single_speaker": self.single_speaker,
            "output_dir": self.output_dir,
            "is_audio": self.is_audio,
            "is_video": self.is_video
        }
        
        params_file = os.path.join(self.task_dir, "00_task_params.json")
        with open(params_file, 'w', encoding='utf-8') as f:
            json.dump(params, f, ensure_ascii=False, indent=2)
        
        return params_file
    
    def load_task_params(self) -> Dict[str, Any]:
        """
        从任务目录加载任务参数
        
        Returns:
            任务参数字典
        """
        params_file = os.path.join(self.task_dir, "00_task_params.json")
        if not os.path.exists(params_file):
            raise FileNotFoundError(f"任务参数文件不存在: {params_file}")
        
        with open(params_file, 'r', encoding='utf-8') as f:
            params = json.load(f)
        
        # 更新上下文属性
        self.source_lang = params.get("source_lang", self.source_lang)
        self.target_lang = params.get("target_lang", self.target_lang)
        self.voice_model = params.get("voice_model", self.voice_model)
        self.single_speaker = params.get("single_speaker", self.single_speaker)
        self.is_audio = params.get("is_audio", self.is_audio)
        self.is_video = params.get("is_video", self.is_video)
        
        return params
    
    def save_metadata(self, metadata: Dict[str, Any]) -> str:
        """
        保存元数据到任务目录
        
        Args:
            metadata: 元数据字典
            
        Returns:
            元数据文件路径
        """
        metadata_file = os.path.join(self.task_dir, "00_metadata.json")
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        return metadata_file
    
    def load_metadata(self) -> Dict[str, Any]:
        """
        从任务目录加载元数据
        
        Returns:
            元数据字典
        """
        metadata_file = os.path.join(self.task_dir, "00_metadata.json")
        if not os.path.exists(metadata_file):
            return {}
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_original_input(self) -> str:
        """
        保存原始输入文件到任务目录
        
        Returns:
            原始输入文件副本路径
        """
        import shutil
        file_ext = os.path.splitext(self.input_path)[1].lower()
        original_file = os.path.join(self.task_dir, f"00_original_input{file_ext}")
        shutil.copy2(self.input_path, original_file)
        return original_file

