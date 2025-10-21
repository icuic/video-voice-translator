"""
音频合成器模块
将翻译后的人声与原始背景音乐合成
"""

import os
import logging
import numpy as np
import librosa
import soundfile as sf
from pathlib import Path
from typing import Dict, Any, Optional
from .utils import validate_file_path, create_output_dir, safe_filename


class AudioMerger:
    """音频合成器类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化音频合成器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 合成配置
        self.merge_config = config.get("audio_merger", {})
        self.target_sample_rate = self.merge_config.get("sample_rate", 16000)
        self.volume_balance = self.merge_config.get("volume_balance", 0.8)  # 人声音量比例
        self.fade_duration = self.merge_config.get("fade_duration", 0.1)  # 淡入淡出时长
    
    def merge_audio(self, vocals_path: str, accompaniment_path: str, 
                   output_path: str) -> Dict[str, Any]:
        """
        合成人声和背景音乐
        
        Args:
            vocals_path: 人声文件路径
            accompaniment_path: 背景音乐文件路径
            output_path: 输出文件路径
            
        Returns:
            合成结果字典
        """
        # 验证输入文件
        if not validate_file_path(vocals_path):
            raise FileNotFoundError(f"人声文件不存在: {vocals_path}")
        if not validate_file_path(accompaniment_path):
            raise FileNotFoundError(f"背景音乐文件不存在: {accompaniment_path}")
        
        self.logger.info(f"开始音频合成: {vocals_path} + {accompaniment_path}")
        
        # 创建输出目录
        create_output_dir(os.path.dirname(output_path))
        
        try:
            # 加载音频文件
            vocals, vocals_sr = librosa.load(vocals_path, sr=self.target_sample_rate)
            accompaniment, accomp_sr = librosa.load(accompaniment_path, sr=self.target_sample_rate)
            
            # 调整音频长度（以较长的为准）
            max_length = max(len(vocals), len(accompaniment))
            vocals = self._pad_or_trim_audio(vocals, max_length)
            accompaniment = self._pad_or_trim_audio(accompaniment, max_length)
            
            # 音量平衡处理
            vocals = self._balance_volume(vocals, accompaniment)
            
            # 合成音频
            merged_audio = vocals + accompaniment
            
            # 应用淡入淡出
            merged_audio = self._apply_fade(merged_audio, vocals_sr)
            
            # 保存合成后的音频
            sf.write(output_path, merged_audio, vocals_sr)
            
            # 获取输出文件信息
            output_size = os.path.getsize(output_path)
            
            result = {
                "success": True,
                "vocals_path": vocals_path,
                "accompaniment_path": accompaniment_path,
                "output_path": output_path,
                "output_size": output_size,
                "duration": len(merged_audio) / vocals_sr,
                "sample_rate": vocals_sr,
                "volume_balance": self.volume_balance
            }
            
            self.logger.info("音频合成完成")
            return result
            
        except Exception as e:
            self.logger.error(f"音频合成失败: {e}")
            raise
    
    def merge_with_original_video_audio(self, translated_vocals_path: str, 
                                       original_audio_path: str, 
                                       output_path: str) -> Dict[str, Any]:
        """
        将翻译后的人声与原始视频音频合成
        
        Args:
            translated_vocals_path: 翻译后的人声文件路径
            original_audio_path: 原始视频音频文件路径
            output_path: 输出文件路径
            
        Returns:
            合成结果字典
        """
        self.logger.info("开始与原始视频音频合成")
        
        try:
            # 首先需要从原始音频中分离出背景音乐
            # 这里假设我们已经有了分离后的背景音乐
            # 在实际应用中，可能需要重新分离原始音频
            
            # 直接合成翻译后的人声和原始音频
            return self.merge_audio(translated_vocals_path, original_audio_path, output_path)
            
        except Exception as e:
            self.logger.error(f"与原始音频合成失败: {e}")
            raise
    
    def _pad_or_trim_audio(self, audio: np.ndarray, target_length: int) -> np.ndarray:
        """
        填充或裁剪音频到目标长度
        
        Args:
            audio: 音频数组
            target_length: 目标长度
            
        Returns:
            处理后的音频数组
        """
        current_length = len(audio)
        
        if current_length < target_length:
            # 填充静音
            padding = np.zeros(target_length - current_length)
            return np.concatenate([audio, padding])
        elif current_length > target_length:
            # 裁剪到目标长度
            return audio[:target_length]
        else:
            return audio
    
    def _balance_volume(self, vocals: np.ndarray, accompaniment: np.ndarray) -> np.ndarray:
        """
        平衡人声和背景音乐的音量
        
        Args:
            vocals: 人声音频
            accompaniment: 背景音乐音频
            
        Returns:
            平衡后的人声音频
        """
        # 计算RMS能量
        vocals_rms = np.sqrt(np.mean(vocals ** 2))
        accomp_rms = np.sqrt(np.mean(accompaniment ** 2))
        
        if accomp_rms > 0:
            # 计算音量比例
            volume_ratio = vocals_rms / accomp_rms
            
            # 应用音量平衡
            if volume_ratio < self.volume_balance:
                # 人声太小声，需要增强
                vocals = vocals * (self.volume_balance / volume_ratio)
            elif volume_ratio > self.volume_balance * 2:
                # 人声太大声，需要减弱
                vocals = vocals * (self.volume_balance * 2 / volume_ratio)
        
        # 防止音频削波
        max_val = np.max(np.abs(vocals))
        if max_val > 0.95:
            vocals = vocals * (0.95 / max_val)
        
        return vocals
    
    def _apply_fade(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        应用淡入淡出效果
        
        Args:
            audio: 音频数组
            sample_rate: 采样率
            
        Returns:
            处理后的音频数组
        """
        fade_samples = int(self.fade_duration * sample_rate)
        
        if len(audio) > 2 * fade_samples:
            # 淡入
            fade_in = np.linspace(0, 1, fade_samples)
            audio[:fade_samples] *= fade_in
            
            # 淡出
            fade_out = np.linspace(1, 0, fade_samples)
            audio[-fade_samples:] *= fade_out
        
        return audio
    
    def merge_with_progress(self, vocals_path: str, accompaniment_path: str, 
                          output_path: str, progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        带进度回调的音频合成
        
        Args:
            vocals_path: 人声文件路径
            accompaniment_path: 背景音乐文件路径
            output_path: 输出文件路径
            progress_callback: 进度回调函数
            
        Returns:
            合成结果字典
        """
        if progress_callback:
            progress_callback(0.0, "开始音频合成...")
        
        # 执行合成
        result = self.merge_audio(vocals_path, accompaniment_path, output_path)
        
        if progress_callback:
            progress_callback(100.0, "音频合成完成")
        
        return result
    
    def get_volume_analysis(self, vocals_path: str, accompaniment_path: str) -> Dict[str, Any]:
        """
        分析人声和背景音乐的音量特征
        
        Args:
            vocals_path: 人声文件路径
            accompaniment_path: 背景音乐文件路径
            
        Returns:
            音量分析结果
        """
        try:
            # 加载音频
            vocals, sr = librosa.load(vocals_path, sr=self.target_sample_rate)
            accompaniment, _ = librosa.load(accompaniment_path, sr=self.target_sample_rate)
            
            # 计算音量特征
            vocals_rms = np.sqrt(np.mean(vocals ** 2))
            accomp_rms = np.sqrt(np.mean(accompaniment ** 2))
            
            # 计算动态范围
            vocals_dynamic = np.max(vocals) - np.min(vocals)
            accomp_dynamic = np.max(accompaniment) - np.min(accompaniment)
            
            # 计算信噪比（人声相对于背景音乐）
            if accomp_rms > 0:
                snr = 20 * np.log10(vocals_rms / accomp_rms)
            else:
                snr = float('inf')
            
            return {
                "vocals_rms": vocals_rms,
                "accompaniment_rms": accomp_rms,
                "vocals_dynamic": vocals_dynamic,
                "accompaniment_dynamic": accomp_dynamic,
                "snr_db": snr,
                "recommended_balance": min(max(vocals_rms / accomp_rms, 0.5), 2.0) if accomp_rms > 0 else 1.0
            }
            
        except Exception as e:
            self.logger.error(f"音量分析失败: {e}")
            return {
                "error": str(e),
                "recommended_balance": 0.8
            }