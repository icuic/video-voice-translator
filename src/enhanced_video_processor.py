"""
增强的视频处理器模块
集成音频分离功能的视频处理器
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from .video_processor import VideoProcessor
from .audio_separator import AudioSeparator
from .audio_merger import AudioMerger
from .utils import validate_file_path, create_output_dir, safe_filename


class EnhancedVideoProcessor(VideoProcessor):
    """增强的视频处理器类，支持音频分离功能"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化增强的视频处理器
        
        Args:
            config_path: 配置文件路径
        """
        # 调用父类初始化
        super().__init__(config_path)
        
        # 初始化音频分离和合成组件
        self.audio_separator = AudioSeparator(self.config)
        self.audio_merger = AudioMerger(self.config)
        
        # 获取音频分离配置
        self.enable_separation = self.config.get("defaults", {}).get("enable_separation", True)
        
        self.logger.info("增强视频处理器初始化完成")
    
    def process_with_separation(self, input_path: str, output_dir: Optional[str] = None, 
                               language: Optional[str] = None, 
                               force_separation: bool = False) -> Dict[str, Any]:
        """
        带音频分离的视频处理
        
        Args:
            input_path: 输入文件路径
            output_dir: 输出目录（可选）
            language: 语言代码（可选）
            force_separation: 强制进行音频分离
            
        Returns:
            处理结果字典
        """
        self.logger.info(f"开始增强处理: {input_path}")
        
        # 验证输入文件
        if not validate_file_path(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")
        
        # 设置默认参数
        if output_dir is None:
            output_dir = self.default_output_dir
        if language is None:
            language = self.default_language
        
        # 创建输出目录
        create_output_dir(output_dir)
        
        try:
            # 1. 基础视频处理（提取音频）
            self.logger.info("执行基础视频处理...")
            basic_result = self.process(input_path, output_dir, language)
            
            if not basic_result["success"]:
                return basic_result
            
            audio_path = basic_result["audio_path"]
            
            # 2. 检测是否需要音频分离
            separation_needed = False
            separation_result = None
            
            if self.enable_separation or force_separation:
                self.logger.info("检测背景音乐...")
                detection_result = self.audio_separator.detect_background_music(audio_path)
                
                if detection_result["has_background_music"]:
                    self.logger.info("检测到背景音乐，开始分离...")
                    separation_result = self.audio_separator.separate_audio(audio_path, output_dir)
                    separation_needed = True
                else:
                    self.logger.info("未检测到背景音乐，跳过分离步骤")
            
            # 3. 构建增强处理结果
            enhanced_result = {
                "success": True,
                "input_path": input_path,
                "output_dir": output_dir,
                "language": language,
                "basic_result": basic_result,
                "separation_needed": separation_needed,
                "separation_result": separation_result,
                "processing_info": {
                    **basic_result["processing_info"],
                    "separation_enabled": separation_needed,
                    "has_background_music": detection_result["has_background_music"] if 'detection_result' in locals() else False
                }
            }
            
            # 4. 添加分离后的文件路径
            if separation_needed and separation_result:
                enhanced_result.update({
                    "vocals_path": separation_result["vocals_path"],
                    "accompaniment_path": separation_result["accompaniment_path"],
                    "separation_quality": separation_result["separation_quality"]
                })
            
            self.logger.info("增强处理完成")
            return enhanced_result
            
        except Exception as e:
            self.logger.error(f"增强处理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "input_path": input_path
            }
    
    def merge_translated_audio(self, translated_vocals_path: str, 
                              original_audio_path: str, 
                              output_path: str) -> Dict[str, Any]:
        """
        合并翻译后的人声与原始背景音乐
        
        Args:
            translated_vocals_path: 翻译后的人声文件路径
            original_audio_path: 原始音频文件路径
            output_path: 输出文件路径
            
        Returns:
            合并结果字典
        """
        self.logger.info("开始合并翻译后音频")
        
        try:
            # 使用音频合成器合并音频
            merge_result = self.audio_merger.merge_audio(
                translated_vocals_path, 
                original_audio_path, 
                output_path
            )
            
            self.logger.info("音频合并完成")
            return merge_result
            
        except Exception as e:
            self.logger.error(f"音频合并失败: {e}")
            raise
    
    def get_separation_recommendation(self, audio_path: str) -> Dict[str, Any]:
        """
        获取音频分离建议
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            分离建议字典
        """
        try:
            detection_result = self.audio_separator.detect_background_music(audio_path)
            
            return {
                "recommendation": detection_result["recommendation"],
                "has_background_music": detection_result["has_background_music"],
                "confidence": detection_result["confidence"],
                "features": detection_result["features"]
            }
            
        except Exception as e:
            self.logger.error(f"获取分离建议失败: {e}")
            return {
                "error": str(e),
                "recommendation": "无法分析音频特征"
            }
    
    def batch_process_with_separation(self, input_paths: list, output_dir: Optional[str] = None,
                                    language: Optional[str] = None) -> Dict[str, Any]:
        """
        批量处理带音频分离
        
        Args:
            input_paths: 输入文件路径列表
            output_dir: 输出目录（可选）
            language: 语言代码（可选）
            
        Returns:
            批量处理结果字典
        """
        self.logger.info(f"开始批量增强处理 {len(input_paths)} 个文件")
        
        results = []
        successful = 0
        failed = 0
        separated = 0
        
        for i, input_path in enumerate(input_paths, 1):
            self.logger.info(f"处理文件 {i}/{len(input_paths)}: {input_path}")
            
            try:
                result = self.process_with_separation(input_path, output_dir, language)
                results.append(result)
                
                if result["success"]:
                    successful += 1
                    if result["separation_needed"]:
                        separated += 1
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
            "separated": separated,
            "results": results
        }
    
    def analyze_audio_complexity(self, audio_path: str) -> Dict[str, Any]:
        """
        分析音频复杂度
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            音频复杂度分析结果
        """
        try:
            detection_result = self.audio_separator.detect_background_music(audio_path)
            features = detection_result["features"]
            
            # 计算复杂度分数
            complexity_score = (
                features["spectral_centroid_std"] / 1000 * 0.3 +
                features["spectral_bandwidth_std"] / 1000 * 0.3 +
                features["mfcc_variance"] / 100 * 0.4
            )
            
            # 分类复杂度
            if complexity_score > 0.7:
                complexity_level = "高"
            elif complexity_score > 0.4:
                complexity_level = "中"
            else:
                complexity_level = "低"
            
            return {
                "complexity_score": complexity_score,
                "complexity_level": complexity_level,
                "recommendation": "强烈建议分离" if complexity_score > 0.6 else "可选分离",
                "features": features
            }
            
        except Exception as e:
            self.logger.error(f"音频复杂度分析失败: {e}")
            return {
                "error": str(e),
                "complexity_level": "未知"
            }
