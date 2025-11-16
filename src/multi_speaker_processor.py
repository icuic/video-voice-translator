"""
多说话者处理流程模块
整合文本翻译、音色克隆、音频合成和视频输出功能
"""

import os
import logging
import json
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from .text_translator import TextTranslator
from .voice_cloner import VoiceCloner
from .audio_synthesizer import AudioSynthesizer
from .media_output_generator import MediaOutputGenerator
from .utils import validate_file_path, create_output_dir, safe_filename
from .pipeline.speaker_binding import SpeakerBinder


class MultiSpeakerProcessor:
    """多说话者处理器类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化多说话者处理器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 初始化各个处理模块
        self.text_translator = TextTranslator(config)
        self.voice_cloner = VoiceCloner(config)
        self.audio_synthesizer = AudioSynthesizer(config)
        self.media_output_generator = MediaOutputGenerator(config)
        self.speaker_binder = SpeakerBinder(config)
        
        # 处理流程配置
        self.processing_config = config.get("multi_speaker_processing", {})
        self.enable_translation = self.processing_config.get("enable_translation", True)
        self.enable_voice_cloning = self.processing_config.get("enable_voice_cloning", True)
        self.enable_audio_synthesis = self.processing_config.get("enable_audio_synthesis", True)
        self.enable_video_output = self.processing_config.get("enable_video_output", True)
        
        self.logger.info("多说话者处理器初始化完成")
    
    def process_segments(self, segments: List[Dict[str, Any]], 
                        background_audio: str, original_video: str,
                        output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        处理多个音频段落
        
        Args:
            segments: 音频段落列表
            background_audio: 背景音乐文件路径
            original_video: 原始视频文件路径
            output_dir: 输出目录
            
        Returns:
            处理结果字典
        """
        if not segments:
            return {
                "success": False,
                "error": "没有提供音频段落"
            }
        
        self.logger.info(f"开始处理 {len(segments)} 个音频段落")
        
        # 创建输出目录
        if output_dir:
            create_output_dir(output_dir)
        
        # 存储处理结果
        processing_results = {
            "segments": segments,
            "translation_results": [],
            "cloning_results": [],
            "synthesis_results": [],
            "generation_results": [],
            "final_segments": []
        }
        
        try:
            # 阶段1: 文本翻译
            if self.enable_translation:
                self.logger.info("阶段1: 开始文本翻译...")
                translation_result = self.text_translator.translate_segments(segments, output_dir)
                processing_results["translation_results"] = translation_result
                
                if translation_result["success"]:
                    segments = translation_result["translated_segments"]
                    self.logger.info(f"文本翻译完成: {len(segments)} 个段落")
                else:
                    self.logger.error("文本翻译失败")
                    return {
                        "success": False,
                        "error": "文本翻译失败",
                        "processing_results": processing_results
                    }
            
            # 阶段2: 音色克隆
            if self.enable_voice_cloning:
                self.logger.info("阶段2: 开始音色克隆...")
                # 在克隆前进行说话人绑定与参考音频稳定
                try:
                    bind_audio_path = self.processing_config.get("original_audio_path")
                    # 若 segments 本身包含全局音频线索，可从首段取用
                    if not bind_audio_path:
                        bind_audio_path = segments[0].get("full_audio_path") or segments[0].get("source_audio_path")
                    segments = self.speaker_binder.bind(bind_audio_path, segments)
                    self.logger.info("说话人绑定完成，已补充 speaker_id/reference_audio_path")
                except Exception as e:
                    self.logger.warning(f"说话人绑定失败，继续原流程: {e}")
                cloning_result = self.voice_cloner.clone_segments(segments, output_dir)
                processing_results["cloning_results"] = cloning_result
                
                if cloning_result["success"]:
                    segments = cloning_result["cloned_segments"]
                    self.logger.info(f"音色克隆完成: {len(segments)} 个段落")
                else:
                    self.logger.error("音色克隆失败")
                    return {
                        "success": False,
                        "error": "音色克隆失败",
                        "processing_results": processing_results
                    }
            
            # 阶段3: 音频合成
            if self.enable_audio_synthesis:
                self.logger.info("阶段3: 开始音频合成...")
                synthesis_result = self.audio_synthesizer.synthesize_segments(
                    segments, background_audio, output_dir
                )
                processing_results["synthesis_results"] = synthesis_result
                
                if synthesis_result["success"]:
                    segments = synthesis_result["synthesized_segments"]
                    self.logger.info(f"音频合成完成: {len(segments)} 个段落")
                else:
                    self.logger.error("音频合成失败")
                    return {
                        "success": False,
                        "error": "音频合成失败",
                        "processing_results": processing_results
                    }
            
            # 阶段4: 视频输出
            if self.enable_video_output:
                self.logger.info("阶段4: 开始视频输出...")
                generation_result = self.media_output_generator.generate_segmented_video(
                    original_video, segments, output_dir
                )
                processing_results["generation_results"] = generation_result
                
                if generation_result["success"]:
                    segments = generation_result["generated_segments"]
                    self.logger.info(f"视频输出完成: {len(segments)} 个段落")
                else:
                    self.logger.error("视频输出失败")
                    return {
                        "success": False,
                        "error": "视频输出失败",
                        "processing_results": processing_results
                    }
            
            # 生成最终报告
            final_report = self._generate_final_report(processing_results)
            
            result = {
                "success": True,
                "total_segments": len(segments),
                "processed_segments": len(segments),
                "final_segments": segments,
                "processing_results": processing_results,
                "final_report": final_report,
                "output_dir": output_dir
            }
            
            self.logger.info(f"所有段落处理完成: {len(segments)} 个段落")
            return result
            
        except Exception as e:
            self.logger.error(f"处理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_results": processing_results
            }
    
    def process_complete_video(self, original_video: str, background_audio: str,
                              output_path: str, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        处理完整视频
        
        Args:
            original_video: 原始视频文件路径
            background_audio: 背景音乐文件路径
            output_path: 输出视频文件路径
            segments: 音频段落列表
            
        Returns:
            处理结果字典
        """
        try:
            self.logger.info("开始处理完整视频...")
            
            # 验证输入文件
            if not validate_file_path(original_video):
                raise FileNotFoundError(f"原始视频文件不存在: {original_video}")
            if not validate_file_path(background_audio):
                raise FileNotFoundError(f"背景音乐文件不存在: {background_audio}")
            
            # 创建输出目录
            output_dir = os.path.dirname(output_path)
            create_output_dir(output_dir)
            
            # 处理段落
            processing_result = self.process_segments(segments, background_audio, original_video, output_dir)
            
            if not processing_result["success"]:
                return processing_result
            
            # 合并所有段落为完整视频
            self.logger.info("合并所有段落为完整视频...")
            merge_result = self._merge_segments_to_video(processing_result["final_segments"], output_path)
            
            if merge_result["success"]:
                result = {
                    "success": True,
                    "original_video": original_video,
                    "background_audio": background_audio,
                    "output_path": output_path,
                    "segments": processing_result["final_segments"],
                    "processing_result": processing_result,
                    "merge_result": merge_result
                }
                self.logger.info(f"完整视频处理完成: {output_path}")
            else:
                result = {
                    "success": False,
                    "error": "视频合并失败",
                    "processing_result": processing_result,
                    "merge_result": merge_result
                }
                self.logger.error("完整视频处理失败")
            
            return result
            
        except Exception as e:
            self.logger.error(f"完整视频处理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "original_video": original_video,
                "background_audio": background_audio,
                "output_path": output_path
            }
    
    def _merge_segments_to_video(self, segments: List[Dict[str, Any]], output_path: str) -> Dict[str, Any]:
        """合并段落为完整视频"""
        try:
            # 创建临时文件列表
            temp_dir = tempfile.mkdtemp()
            segment_list_file = os.path.join(temp_dir, "segments.txt")
            
            # 写入段落列表
            with open(segment_list_file, 'w', encoding='utf-8') as f:
                for segment in segments:
                    video_path = segment.get("generated_video_path", "")
                    if video_path and os.path.exists(video_path):
                        f.write(f"file '{video_path}'\n")
            
            # 使用FFmpeg合并视频
            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", segment_list_file,
                "-c", "copy",
                "-y",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            # 清理临时文件
            import shutil
            shutil.rmtree(temp_dir)
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "output_path": output_path,
                    "segments_count": len(segments)
                }
            else:
                return {
                    "success": False,
                    "error": f"FFmpeg合并失败: {result.stderr}",
                    "segments_count": len(segments)
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "segments_count": len(segments)
            }
    
    def _generate_final_report(self, processing_results: Dict[str, Any]) -> Dict[str, Any]:
        """生成最终处理报告"""
        try:
            # 统计各个阶段的结果
            translation_success = 0
            cloning_success = 0
            synthesis_success = 0
            generation_success = 0
            
            if processing_results.get("translation_results", {}).get("success", False):
                translation_success = processing_results["translation_results"]["successful_translations"]
            
            if processing_results.get("cloning_results", {}).get("success", False):
                cloning_success = processing_results["cloning_results"]["successful_clonings"]
            
            if processing_results.get("synthesis_results", {}).get("success", False):
                synthesis_success = processing_results["synthesis_results"]["successful_syntheses"]
            
            if processing_results.get("generation_results", {}).get("success", False):
                generation_success = processing_results["generation_results"]["successful_generations"]
            
            # 计算总体成功率
            total_segments = len(processing_results["segments"])
            overall_success_rate = (
                translation_success + cloning_success + synthesis_success + generation_success
            ) / (total_segments * 4) if total_segments > 0 else 0
            
            report = {
                "total_segments": total_segments,
                "translation_success": translation_success,
                "cloning_success": cloning_success,
                "synthesis_success": synthesis_success,
                "generation_success": generation_success,
                "overall_success_rate": overall_success_rate,
                "processing_stages": {
                    "translation": processing_results.get("translation_results", {}).get("success", False),
                    "cloning": processing_results.get("cloning_results", {}).get("success", False),
                    "synthesis": processing_results.get("synthesis_results", {}).get("success", False),
                    "generation": processing_results.get("generation_results", {}).get("success", False)
                }
            }
            
            return report
            
        except Exception as e:
            self.logger.error(f"生成最终报告失败: {e}")
            return {
                "error": str(e),
                "total_segments": len(processing_results.get("segments", []))
            }

