"""
视频处理主模块
整合元数据提取和音频提取功能，提供统一的视频处理接口
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


class VideoProcessor:
    """视频处理主类"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化视频处理器
        
        Args:
            config_path: 配置文件路径
        """
        # 加载配置
        self.config = load_config(config_path)
        
        # 设置日志
        setup_logging(self.config)
        self.logger = logging.getLogger(__name__)
        
        # 初始化组件
        self.metadata_extractor = MetadataExtractor()
        self.audio_extractor = AudioExtractor(self.config)
        
        # 获取配置参数
        self.supported_formats = self.config.get("video", {}).get("supported_formats", 
                                                                  ["mp4", "avi", "mov", "mkv", "mp3", "wav"])
        self.default_language = self.config.get("defaults", {}).get("language", "en")
        self.default_output_dir = self.config.get("defaults", {}).get("output_dir", "./output")
        
        self.logger.info("视频处理器初始化完成")
    
    def process(self, input_path: str, output_dir: Optional[str] = None, 
                language: Optional[str] = None) -> Dict[str, Any]:
        """
        处理视频或音频文件
        
        Args:
            input_path: 输入文件路径
            output_dir: 输出目录（可选）
            language: 语言代码（可选，默认为英语）
            
        Returns:
            处理结果字典
        """
        self.logger.info(f"开始处理文件: {input_path}")
        
        # 验证输入文件
        if not validate_file_path(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")
        
        # 验证文件格式
        if not validate_file_format(input_path, self.supported_formats):
            raise ValueError(f"不支持的文件格式: {Path(input_path).suffix}")
        
        # 设置默认参数
        if output_dir is None:
            output_dir = self.default_output_dir
        if language is None:
            language = self.default_language
        
        # 创建输出目录
        create_output_dir(output_dir)
        
        try:
            # 1. 提取元数据
            self.logger.info("提取文件元数据...")
            metadata = self.metadata_extractor.extract(input_path)
            
            # 2. 生成输出文件名
            input_name = Path(input_path).stem
            safe_name = safe_filename(input_name)
            audio_output_path = os.path.join(output_dir, f"{safe_name}_audio.wav")
            
            # 3. 提取音频
            self.logger.info("提取音频...")
            audio_result = self.audio_extractor.extract(input_path, audio_output_path)
            
            # 4. 构建处理结果
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
    
    def batch_process(self, input_paths: list, output_dir: Optional[str] = None,
                     language: Optional[str] = None) -> Dict[str, Any]:
        """
        批量处理文件
        
        Args:
            input_paths: 输入文件路径列表
            output_dir: 输出目录（可选）
            language: 语言代码（可选）
            
        Returns:
            批量处理结果字典
        """
        self.logger.info(f"开始批量处理 {len(input_paths)} 个文件")
        
        results = []
        successful = 0
        failed = 0
        
        for i, input_path in enumerate(input_paths, 1):
            self.logger.info(f"处理文件 {i}/{len(input_paths)}: {input_path}")
            
            try:
                result = self.process(input_path, output_dir, language)
                results.append(result)
                
                if result["success"]:
                    successful += 1
                else:
                    failed += 1
                    
            except Exception as e:
                self.logger.error(f"处理文件失败 {input_path}: {e}")
                results.append({
                    "success": False,
                    "error": str(e),
                    "input_path": input_path
                })
                failed += 1
        
        return {
            "total": len(input_paths),
            "successful": successful,
            "failed": failed,
            "results": results
        }
    
    def get_supported_formats(self) -> list:
        """
        获取支持的文件格式列表
        
        Returns:
            支持的格式列表
        """
        return self.supported_formats.copy()
    
    def validate_input(self, input_path: str) -> Dict[str, Any]:
        """
        验证输入文件
        
        Args:
            input_path: 输入文件路径
            
        Returns:
            验证结果字典
        """
        result = {
            "valid": False,
            "errors": [],
            "warnings": []
        }
        
        # 检查文件是否存在
        if not validate_file_path(input_path):
            result["errors"].append("文件不存在")
            return result
        
        # 检查文件格式
        if not validate_file_format(input_path, self.supported_formats):
            result["errors"].append(f"不支持的文件格式: {Path(input_path).suffix}")
            return result
        
        # 检查文件大小
        file_size = os.path.getsize(input_path)
        if file_size == 0:
            result["errors"].append("文件为空")
            return result
        
        # 检查文件大小警告（超过1GB）
        if file_size > 1024 * 1024 * 1024:
            result["warnings"].append("文件较大，处理时间可能较长")
        
        result["valid"] = True
        return result
    
    def _get_duration(self, metadata: Dict[str, Any]) -> float:
        """
        从元数据中获取时长
        
        Args:
            metadata: 元数据字典
            
        Returns:
            时长（秒）
        """
        # 优先从format信息获取
        if "format" in metadata and "duration" in metadata["format"]:
            return metadata["format"]["duration"]
        
        # 从视频信息获取
        if "video" in metadata and "duration" in metadata["video"]:
            return metadata["video"]["duration"]
        
        # 从音频信息获取
        if "audio" in metadata and "duration" in metadata["audio"]:
            return metadata["audio"]["duration"]
        
        return 0.0
    
    def get_processing_info(self, input_path: str) -> Dict[str, Any]:
        """
        获取文件处理信息（不实际处理）
        
        Args:
            input_path: 输入文件路径
            
        Returns:
            处理信息字典
        """
        # 验证输入
        validation = self.validate_input(input_path)
        if not validation["valid"]:
            return {
                "valid": False,
                "errors": validation["errors"]
            }
        
        try:
            # 提取元数据
            metadata = self.metadata_extractor.extract(input_path)
            
            return {
                "valid": True,
                "metadata": metadata,
                "estimated_processing_time": self._estimate_processing_time(metadata),
                "warnings": validation["warnings"]
            }
            
        except Exception as e:
            return {
                "valid": False,
                "errors": [str(e)]
            }
    
    def _estimate_processing_time(self, metadata: Dict[str, Any]) -> float:
        """
        估算处理时间
        
        Args:
            metadata: 元数据字典
            
        Returns:
            估算的处理时间（秒）
        """
        duration = self._get_duration(metadata)
        
        # 基于经验值估算：音频提取时间约为文件时长的1/10到1/5
        if duration > 0:
            return duration * 0.2  # 假设处理速度是播放速度的5倍
        
        return 0.0



