"""
音频合成模块
将中文语音与背景音乐合并，保持音频质量和时间同步
"""

import os
import logging
import json
import numpy as np
import librosa
import soundfile as sf
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from .utils import validate_file_path, create_output_dir, safe_filename


class AudioSynthesizer:
    """音频合成器类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化音频合成器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 音频合成配置
        self.synthesis_config = config.get("audio_synthesis", {})
        self.sample_rate = self.synthesis_config.get("sample_rate", 16000)
        self.volume_balance = self.synthesis_config.get("volume_balance", 0.8)
        self.fade_duration = self.synthesis_config.get("fade_duration", 0.1)
        self.noise_reduction = self.synthesis_config.get("noise_reduction", True)
        self.audio_quality = self.synthesis_config.get("audio_quality", "high")
        
        # 初始化音频处理参数
        self._init_audio_params()
    
    def _init_audio_params(self):
        """初始化音频处理参数"""
        # 根据音频质量设置参数
        if self.audio_quality == "high":
            self.bit_depth = 24
            self.dither = True
        elif self.audio_quality == "medium":
            self.bit_depth = 16
            self.dither = True
        else:  # low
            self.bit_depth = 16
            self.dither = False
        
        self.logger.info(f"音频合成器初始化完成 - 质量: {self.audio_quality}")
    
    def synthesize_audio(self, voice_audio: str, background_audio: str, 
                        output_path: str, start_time: float = 0.0, 
                        end_time: Optional[float] = None) -> Dict[str, Any]:
        """
        合成单个音频
        
        Args:
            voice_audio: 人声音频文件路径
            background_audio: 背景音乐文件路径
            output_path: 输出音频文件路径
            start_time: 开始时间（秒）
            end_time: 结束时间（秒，可选）
            
        Returns:
            合成结果字典
        """
        try:
            self.logger.info(f"开始音频合成: {voice_audio} + {background_audio}")
            
            # 验证输入文件
            if not validate_file_path(voice_audio):
                raise FileNotFoundError(f"人声音频文件不存在: {voice_audio}")
            if not validate_file_path(background_audio):
                raise FileNotFoundError(f"背景音乐文件不存在: {background_audio}")
            
            # 创建输出目录
            output_dir = os.path.dirname(output_path)
            create_output_dir(output_dir)
            
            # 加载音频文件
            voice_data, voice_sr = self._load_audio(voice_audio)
            background_data, background_sr = self._load_audio(background_audio)
            
            # 统一采样率
            if voice_sr != self.sample_rate:
                voice_data = librosa.resample(voice_data, orig_sr=voice_sr, target_sr=self.sample_rate)
            if background_sr != self.sample_rate:
                background_data = librosa.resample(background_data, orig_sr=background_sr, target_sr=self.sample_rate)
            
            # 处理背景音乐
            processed_background = self._process_background_audio(background_data, start_time, end_time)
            
            # 处理人声音频
            processed_voice = self._process_voice_audio(voice_data)
            
            # 合成音频
            synthesized_audio = self._mix_audio(processed_voice, processed_background)
            
            # 后处理
            final_audio = self._postprocess_audio(synthesized_audio)
            
            # 保存合成音频
            self._save_audio(final_audio, output_path)
            
            result = {
                "success": True,
                "voice_audio": voice_audio,
                "background_audio": background_audio,
                "output_path": output_path,
                "start_time": start_time,
                "end_time": end_time,
                "processing_info": {
                    "sample_rate": self.sample_rate,
                    "duration": len(final_audio) / self.sample_rate,
                    "volume_balance": self.volume_balance,
                    "audio_quality": self.audio_quality
                }
            }
            
            self.logger.info(f"音频合成完成: {output_path}")
            return result
            
        except Exception as e:
            self.logger.error(f"音频合成失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_audio": voice_audio,
                "background_audio": background_audio,
                "output_path": output_path
            }
    
    def synthesize_segments(self, segments: List[Dict[str, Any]], 
                          background_audio: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        合成多个音频段落
        
        Args:
            segments: 音频段落列表
            background_audio: 背景音乐文件路径
            output_dir: 输出目录
            
        Returns:
            合成结果字典
        """
        if not segments:
            return {
                "success": False,
                "error": "没有提供音频段落"
            }
        
        self.logger.info(f"开始合成 {len(segments)} 个音频段落")
        
        # 创建输出目录
        if output_dir:
            create_output_dir(output_dir)
        
        synthesized_segments = []
        synthesis_results = []
        
        try:
            for i, segment in enumerate(segments):
                self.logger.info(f"合成段落 {i+1}/{len(segments)}")
                
                # 获取段落信息
                voice_audio = segment.get("cloned_audio_path", "")
                start_time = segment.get("start_time", 0)
                end_time = segment.get("end_time", 0)
                
                if not voice_audio:
                    self.logger.warning(f"段落 {i+1} 缺少人声音频")
                    continue
                
                # 生成输出文件名
                output_filename = f"synthesized_{i:02d}.wav"
                output_path = os.path.join(output_dir, output_filename) if output_dir else f"output/synthesized_{i:02d}.wav"
                
                # 执行音频合成
                synthesis_result = self.synthesize_audio(
                    voice_audio, background_audio, output_path, start_time, end_time
                )
                synthesis_results.append(synthesis_result)
                
                if synthesis_result["success"]:
                    # 创建合成后的段落
                    synthesized_segment = {
                        **segment,
                        "synthesized_audio_path": output_path,
                        "synthesis_info": synthesis_result["processing_info"]
                    }
                    synthesized_segments.append(synthesized_segment)
                    
                    # 保存合成结果到文件
                    if output_dir:
                        self._save_synthesis_result(synthesized_segment, output_dir, i)
                
                self.logger.info(f"段落 {i+1} 合成完成")
            
            # 生成合成报告
            synthesis_report = self._generate_synthesis_report(synthesis_results)
            
            result = {
                "success": True,
                "total_segments": len(segments),
                "synthesized_segments": len(synthesized_segments),
                "synthesized_segments": synthesized_segments,
                "synthesis_results": synthesis_results,
                "synthesis_report": synthesis_report,
                "output_dir": output_dir
            }
            
            self.logger.info(f"所有段落合成完成: {len(synthesized_segments)}/{len(segments)}")
            return result
            
        except Exception as e:
            self.logger.error(f"批量合成失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "synthesized_segments": synthesized_segments,
                "synthesis_results": synthesis_results
            }
    
    def _load_audio(self, audio_path: str) -> Tuple[np.ndarray, int]:
        """加载音频文件"""
        try:
            audio_data, sample_rate = librosa.load(audio_path, sr=None)
            self.logger.info(f"加载音频: {audio_path} (采样率: {sample_rate})")
            return audio_data, sample_rate
        except Exception as e:
            self.logger.error(f"加载音频失败: {e}")
            raise
    
    def _process_background_audio(self, background_data: np.ndarray, 
                                start_time: float, end_time: Optional[float]) -> np.ndarray:
        """处理背景音乐"""
        try:
            # 计算开始和结束样本
            start_sample = int(start_time * self.sample_rate)
            if end_time is not None:
                end_sample = int(end_time * self.sample_rate)
            else:
                end_sample = len(background_data)
            
            # 提取指定时间段的背景音乐
            if start_sample < len(background_data):
                processed = background_data[start_sample:end_sample]
            else:
                # 如果开始时间超出背景音乐长度，使用循环
                processed = background_data[start_sample % len(background_data):]
            
            # 调整音量
            processed = processed * (1 - self.volume_balance)
            
            # 应用淡入淡出
            if self.fade_duration > 0:
                fade_samples = int(self.fade_duration * self.sample_rate)
                if len(processed) > fade_samples * 2:
                    # 淡入
                    processed[:fade_samples] *= np.linspace(0, 1, fade_samples)
                    # 淡出
                    processed[-fade_samples:] *= np.linspace(1, 0, fade_samples)
            
            return processed
            
        except Exception as e:
            self.logger.error(f"处理背景音乐失败: {e}")
            raise
    
    def _process_voice_audio(self, voice_data: np.ndarray) -> np.ndarray:
        """处理人声音频"""
        try:
            # 调整音量
            processed = voice_data * self.volume_balance
            
            # 降噪处理
            if self.noise_reduction:
                processed = self._apply_noise_reduction(processed)
            
            # 应用淡入淡出
            if self.fade_duration > 0:
                fade_samples = int(self.fade_duration * self.sample_rate)
                if len(processed) > fade_samples * 2:
                    # 淡入
                    processed[:fade_samples] *= np.linspace(0, 1, fade_samples)
                    # 淡出
                    processed[-fade_samples:] *= np.linspace(1, 0, fade_samples)
            
            return processed
            
        except Exception as e:
            self.logger.error(f"处理人声音频失败: {e}")
            raise
    
    def _apply_noise_reduction(self, audio_data: np.ndarray) -> np.ndarray:
        """应用降噪处理"""
        try:
            # 简单的降噪处理
            # 这里可以使用更复杂的降噪算法，如Wiener滤波等
            
            # 计算噪声阈值
            noise_threshold = np.percentile(np.abs(audio_data), 10)
            
            # 应用软阈值
            processed = np.where(
                np.abs(audio_data) < noise_threshold,
                audio_data * 0.1,  # 降低噪声
                audio_data
            )
            
            return processed
            
        except Exception as e:
            self.logger.error(f"降噪处理失败: {e}")
            return audio_data
    
    def _mix_audio(self, voice_data: np.ndarray, background_data: np.ndarray) -> np.ndarray:
        """混合音频"""
        try:
            # 确保两个音频长度一致
            max_length = max(len(voice_data), len(background_data))
            
            # 填充较短的音频
            if len(voice_data) < max_length:
                voice_data = np.pad(voice_data, (0, max_length - len(voice_data)), 'constant')
            if len(background_data) < max_length:
                background_data = np.pad(background_data, (0, max_length - len(background_data)), 'constant')
            
            # 混合音频
            mixed_audio = voice_data + background_data
            
            # 防止削波
            max_amplitude = np.max(np.abs(mixed_audio))
            if max_amplitude > 1.0:
                mixed_audio = mixed_audio / max_amplitude * 0.95
            
            return mixed_audio
            
        except Exception as e:
            self.logger.error(f"混合音频失败: {e}")
            raise
    
    def _postprocess_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """后处理音频"""
        try:
            # 归一化
            max_amplitude = np.max(np.abs(audio_data))
            if max_amplitude > 0:
                audio_data = audio_data / max_amplitude * 0.95
            
            # 应用抖动（如果启用）
            if self.dither:
                dither_noise = np.random.normal(0, 1e-6, len(audio_data))
                audio_data = audio_data + dither_noise
            
            return audio_data
            
        except Exception as e:
            self.logger.error(f"后处理音频失败: {e}")
            raise
    
    def _save_audio(self, audio_data: np.ndarray, output_path: str):
        """保存音频文件"""
        try:
            # 根据位深度选择数据类型
            if self.bit_depth == 24:
                # 24位音频
                audio_data = (audio_data * 8388607).astype(np.int32)
                sf.write(output_path, audio_data, self.sample_rate, subtype='PCM_24')
            elif self.bit_depth == 16:
                # 16位音频
                audio_data = (audio_data * 32767).astype(np.int16)
                sf.write(output_path, audio_data, self.sample_rate, subtype='PCM_16')
            else:
                # 默认32位浮点
                sf.write(output_path, audio_data, self.sample_rate, subtype='FLOAT')
            
            self.logger.info(f"音频已保存: {output_path}")
            
        except Exception as e:
            self.logger.error(f"保存音频失败: {e}")
            raise
    
    def _save_synthesis_result(self, segment: Dict[str, Any], output_dir: str, index: int):
        """保存合成结果到文件"""
        try:
            # 创建合成结果文件
            result_file = os.path.join(output_dir, f"synthesis_{index:02d}.json")
            
            result_data = {
                "segment_id": index,
                "original_text": segment.get("original_text", ""),
                "translated_text": segment.get("translated_text", ""),
                "synthesized_audio_path": segment.get("synthesized_audio_path", ""),
                "start_time": segment.get("start_time", 0),
                "end_time": segment.get("end_time", 0),
                "duration": segment.get("duration", 0),
                "synthesis_info": segment.get("synthesis_info", {})
            }
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"合成结果已保存: {result_file}")
            
        except Exception as e:
            self.logger.error(f"保存合成结果失败: {e}")
    
    def _generate_synthesis_report(self, synthesis_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成合成报告"""
        total_segments = len(synthesis_results)
        successful_syntheses = sum(1 for result in synthesis_results if result.get("success", False))
        
        # 计算合成质量指标
        durations = [result.get("processing_info", {}).get("duration", 0) for result in synthesis_results]
        
        report = {
            "total_segments": total_segments,
            "successful_syntheses": successful_syntheses,
            "success_rate": successful_syntheses / total_segments if total_segments > 0 else 0,
            "average_duration": sum(durations) / len(durations) if durations else 0,
            "sample_rate": self.sample_rate,
            "volume_balance": self.volume_balance,
            "audio_quality": self.audio_quality
        }
        
        return report

