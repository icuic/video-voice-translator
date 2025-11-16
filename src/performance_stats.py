"""
性能统计管理器

负责记录和管理视频翻译系统的性能统计数据，包括：
- 各步骤的耗时统计
- 视频基本信息记录
- 配置参数记录
- 数据保存和导出功能
"""

import os
import json
import csv
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path


class PerformanceStats:
    """性能统计管理器"""
    
    def __init__(self, video_info: Dict[str, Any], config: Dict[str, Any]):
        """
        初始化性能统计管理器
        
        Args:
            video_info: 视频基本信息
            config: 系统配置
        """
        self.logger = logging.getLogger(__name__)
        
        # 基本信息
        self.timestamp = datetime.now().isoformat()
        self.video_info = video_info.copy()
        self.config = config.copy()
        
        # 时间记录
        self.start_time = time.time()
        self.step_times = {}  # 存储各步骤的开始时间
        self.step_durations = {}  # 存储各步骤的耗时
        self.step_metadata = {}  # 存储各步骤的元数据
        
        # 步骤定义
        self.step_names = [
            "audio_extraction",
            "audio_separation", 
            "speech_recognition",
            "text_translation",
            "reference_audio_extraction",
            "voice_cloning",
            "audio_merging",
            "video_generation"
        ]
        
        self.logger.info("性能统计管理器初始化完成")
    
    def start_step(self, step_name: str) -> None:
        """
        开始记录某个步骤的时间
        
        Args:
            step_name: 步骤名称
        """
        if step_name not in self.step_names:
            self.logger.warning(f"未知步骤名称: {step_name}")
            return
            
        self.step_times[step_name] = time.time()
        self.logger.debug(f"开始记录步骤: {step_name}")
    
    def end_step(self, step_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        结束记录某个步骤的时间
        
        Args:
            step_name: 步骤名称
            metadata: 步骤元数据（如分段数量、状态等）
        """
        if step_name not in self.step_times:
            self.logger.warning(f"步骤 {step_name} 未开始记录")
            return
            
        start_time = self.step_times[step_name]
        duration = time.time() - start_time
        
        self.step_durations[step_name] = duration
        
        if metadata:
            self.step_metadata[step_name] = metadata.copy()
        else:
            self.step_metadata[step_name] = {"status": "success"}
            
        self.logger.debug(f"步骤 {step_name} 完成，耗时: {duration:.2f}秒")
    
    def set_video_info(self, video_duration: float, resolution: str = "", fps: float = 0.0) -> None:
        """
        设置视频详细信息
        
        Args:
            video_duration: 视频时长（秒）
            resolution: 分辨率（如 "1920x1080"）
            fps: 帧率
        """
        self.video_info.update({
            "duration_seconds": video_duration,
            "duration_formatted": self._format_duration(video_duration),
            "resolution": resolution,
            "fps": fps
        })
        
        self.logger.info(f"视频信息已设置: {video_duration:.1f}秒, {resolution}, {fps}fps")
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取性能统计摘要
        
        Returns:
            包含所有统计信息的字典
        """
        total_time = time.time() - self.start_time
        video_duration = self.video_info.get("duration_seconds", 0)
        speed_ratio = total_time / video_duration if video_duration > 0 else 0
        
        # 构建步骤信息
        steps_info = {}
        for step_name in self.step_names:
            if step_name in self.step_durations:
                step_info = {
                    "duration": round(self.step_durations[step_name], 2),
                    "status": self.step_metadata.get(step_name, {}).get("status", "success")
                }
                # 添加元数据
                if step_name in self.step_metadata:
                    step_info.update(self.step_metadata[step_name])
                steps_info[step_name] = step_info
        
        # 构建配置信息
        config_info = {}
        if "whisper" in self.config:
            whisper_config = self.config["whisper"]
            config_info.update({
                "whisper_model": whisper_config.get("model_size", "unknown"),
                "whisper_backend": whisper_config.get("backend", "whisper"),
                "segmentation_method": whisper_config.get("segmentation", {}).get("method", "unknown"),
                "fp16": whisper_config.get("fp16", False)
            })
        
        if "voice_cloning" in self.config:
            config_info["voice_model"] = self.config["voice_cloning"].get("model", "unknown")
        
        summary = {
            "timestamp": self.timestamp,
            "video_info": self.video_info,
            "total_time": {
                "seconds": round(total_time, 2),
                "formatted": self._format_duration(total_time),
                "speed_ratio": round(speed_ratio, 2)
            },
            "steps": steps_info,
            "config": config_info
        }
        
        return summary
    
    def save_to_json(self, output_path: str) -> None:
        """
        保存统计数据为 JSON 格式
        
        Args:
            output_path: 输出文件路径
        """
        try:
            summary = self.get_summary()
            
            # 确保目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
                
            self.logger.info(f"性能统计 JSON 已保存: {output_path}")
            
        except Exception as e:
            self.logger.error(f"保存 JSON 统计失败: {e}")
    
    def save_to_csv(self, output_path: str) -> None:
        """
        保存统计数据为 CSV 格式
        
        Args:
            output_path: 输出文件路径
        """
        try:
            summary = self.get_summary()
            
            # 确保目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 准备 CSV 数据
            csv_data = {
                "timestamp": summary["timestamp"],
                "filename": summary["video_info"].get("filename", ""),
                "video_duration": summary["video_info"].get("duration_seconds", 0),
                "total_time": summary["total_time"]["seconds"],
                "speed_ratio": summary["total_time"]["speed_ratio"],
                "segments": self._get_segment_count(summary["steps"]),
                "whisper_model": summary["config"].get("whisper_model", ""),
                "whisper_backend": summary["config"].get("whisper_backend", ""),
                "segmentation_method": summary["config"].get("segmentation_method", ""),
                "fp16": summary["config"].get("fp16", False),
                "voice_model": summary["config"].get("voice_model", "")
            }
            
            # 添加各步骤耗时
            for step_name in self.step_names:
                if step_name in summary["steps"]:
                    csv_data[step_name] = summary["steps"][step_name]["duration"]
                else:
                    csv_data[step_name] = 0
            
            # 写入 CSV
            file_exists = os.path.exists(output_path)
            with open(output_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=csv_data.keys())
                
                # 如果是新文件，写入表头
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow(csv_data)
            
            self.logger.info(f"性能统计 CSV 已保存: {output_path}")
            
        except Exception as e:
            self.logger.error(f"保存 CSV 统计失败: {e}")
    
    def append_to_global_stats(self, stats_dir: str = None) -> None:
        """
        追加到全局统计文件
        
        Args:
            stats_dir: 统计目录路径，如果为None则从配置读取或使用默认值
        """
        try:
            # 如果没有指定stats_dir，从配置读取或使用默认值
            if stats_dir is None:
                stats_dir = self.config.get("stats", {}).get("stats_dir", "data/stats")
            
            # 确保统计目录存在
            os.makedirs(stats_dir, exist_ok=True)
            
            # 保存到全局 JSON 文件
            json_path = os.path.join(stats_dir, "translation_history.json")
            self._append_to_json_history(json_path)
            
            # 保存到全局 CSV 文件
            csv_path = os.path.join(stats_dir, "translation_history.csv")
            self.save_to_csv(csv_path)
            
            self.logger.info(f"已追加到全局统计: {stats_dir}")
            
        except Exception as e:
            self.logger.error(f"追加全局统计失败: {e}")
    
    def _append_to_json_history(self, json_path: str) -> None:
        """
        追加到 JSON 历史记录
        
        Args:
            json_path: JSON 文件路径
        """
        try:
            summary = self.get_summary()
            
            # 读取现有历史记录
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            else:
                history = []
            
            # 添加新记录
            history.append(summary)
            
            # 保存更新后的历史记录
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.logger.error(f"追加 JSON 历史记录失败: {e}")
    
    def _format_duration(self, seconds: float) -> str:
        """
        格式化时长显示
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化的时长字符串
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.1f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours}h {minutes}m {secs:.1f}s"
    
    def _get_segment_count(self, steps: Dict[str, Any]) -> int:
        """
        获取分段数量
        
        Args:
            steps: 步骤信息
            
        Returns:
            分段数量
        """
        # 优先从语音识别步骤获取
        if "speech_recognition" in steps:
            return steps["speech_recognition"].get("segments", 0)
        
        # 其次从音色克隆步骤获取
        if "voice_cloning" in steps:
            return steps["voice_cloning"].get("segments", 0)
        
        return 0
