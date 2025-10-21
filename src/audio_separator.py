"""
音频分离器模块
使用Spleeter进行人声和背景音乐的分离
"""

import os
import logging
import numpy as np
import librosa
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from spleeter.separator import Separator
from spleeter.audio.adapter import AudioAdapter
from .utils import validate_file_path, create_output_dir, safe_filename


class AudioSeparator:
    """音频分离器类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化音频分离器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 初始化Spleeter分离器
        try:
            # 使用2stems模型（人声+伴奏）
            self.separator = Separator('spleeter:2stems-16kHz')
            self.audio_adapter = AudioAdapter.default()
            self.logger.info("Spleeter分离器初始化成功")
        except Exception as e:
            self.logger.error(f"Spleeter初始化失败: {e}")
            raise
        
        # 分离配置
        self.separation_config = config.get("audio_separation", {})
        self.enable_gpu = self.separation_config.get("enable_gpu", True)
        self.quality_threshold = self.separation_config.get("quality_threshold", 0.3)
    
    def detect_background_music(self, audio_path: str) -> Dict[str, Any]:
        """
        检测音频中是否包含背景音乐
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            检测结果字典
        """
        if not validate_file_path(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        self.logger.info(f"开始检测背景音乐: {audio_path}")
        
        try:
            # 加载音频文件
            waveform, sample_rate = librosa.load(audio_path, sr=16000)
            
            # 分析音频特征
            features = self._analyze_audio_features(waveform, sample_rate)
            
            # 判断是否有背景音乐
            has_background = self._classify_background_music(features)
            
            result = {
                "has_background_music": has_background,
                "confidence": features["confidence"],
                "features": features,
                "recommendation": self._get_separation_recommendation(has_background, features)
            }
            
            self.logger.info(f"背景音乐检测完成: {has_background}")
            return result
            
        except Exception as e:
            self.logger.error(f"背景音乐检测失败: {e}")
            raise
    
    def separate_audio(self, audio_path: str, output_dir: str) -> Dict[str, Any]:
        """
        分离音频为人声和背景音乐
        
        Args:
            audio_path: 输入音频文件路径
            output_dir: 输出目录
            
        Returns:
            分离结果字典
        """
        if not validate_file_path(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        self.logger.info(f"开始音频分离: {audio_path}")
        
        # 创建输出目录
        create_output_dir(output_dir)
        
        try:
            # 生成输出文件名
            input_name = Path(audio_path).stem
            safe_name = safe_filename(input_name)
            
            # 执行分离
            self.separator.separate_to_file(
                audio_path,
                output_dir,
                filename_format=f"{safe_name}_{{instrument}}.wav"
            )
            
            # 生成输出文件路径
            vocals_path = os.path.join(output_dir, f"{safe_name}_vocals.wav")
            accompaniment_path = os.path.join(output_dir, f"{safe_name}_accompaniment.wav")
            
            # 验证输出文件
            if not os.path.exists(vocals_path) or not os.path.exists(accompaniment_path):
                raise RuntimeError("音频分离失败，输出文件未生成")
            
            # 获取文件信息
            vocals_size = os.path.getsize(vocals_path)
            accompaniment_size = os.path.getsize(accompaniment_path)
            
            result = {
                "success": True,
                "input_path": audio_path,
                "output_dir": output_dir,
                "vocals_path": vocals_path,
                "accompaniment_path": accompaniment_path,
                "vocals_size": vocals_size,
                "accompaniment_size": accompaniment_size,
                "separation_quality": self._evaluate_separation_quality(vocals_path, accompaniment_path)
            }
            
            self.logger.info("音频分离完成")
            return result
            
        except Exception as e:
            self.logger.error(f"音频分离失败: {e}")
            raise
    
    def separate_with_progress(self, audio_path: str, output_dir: str, 
                             progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        带进度回调的音频分离
        
        Args:
            audio_path: 输入音频文件路径
            output_dir: 输出目录
            progress_callback: 进度回调函数
            
        Returns:
            分离结果字典
        """
        if progress_callback:
            progress_callback(0.0, "开始音频分离...")
        
        # 执行分离
        result = self.separate_audio(audio_path, output_dir)
        
        if progress_callback:
            progress_callback(100.0, "音频分离完成")
        
        return result
    
    def _analyze_audio_features(self, waveform: np.ndarray, sample_rate: int) -> Dict[str, Any]:
        """
        分析音频特征
        
        Args:
            waveform: 音频波形
            sample_rate: 采样率
            
        Returns:
            音频特征字典
        """
        # 计算频谱特征
        stft = librosa.stft(waveform)
        magnitude = np.abs(stft)
        
        # 计算频谱质心（音色特征）
        spectral_centroids = librosa.feature.spectral_centroid(y=waveform, sr=sample_rate)[0]
        
        # 计算频谱带宽（复杂度特征）
        spectral_bandwidth = librosa.feature.spectral_bandwidth(y=waveform, sr=sample_rate)[0]
        
        # 计算零交叉率（语音特征）
        zcr = librosa.feature.zero_crossing_rate(waveform)[0]
        
        # 计算MFCC特征
        mfccs = librosa.feature.mfcc(y=waveform, sr=sample_rate, n_mfcc=13)
        
        # 计算特征统计
        features = {
            "spectral_centroid_mean": np.mean(spectral_centroids),
            "spectral_centroid_std": np.std(spectral_centroids),
            "spectral_bandwidth_mean": np.mean(spectral_bandwidth),
            "spectral_bandwidth_std": np.std(spectral_bandwidth),
            "zcr_mean": np.mean(zcr),
            "zcr_std": np.std(zcr),
            "mfcc_variance": np.var(mfccs, axis=1).mean(),
            "energy": np.sum(magnitude ** 2),
            "duration": len(waveform) / sample_rate
        }
        
        return features
    
    def _classify_background_music(self, features: Dict[str, Any]) -> bool:
        """
        基于音频特征分类是否有背景音乐
        
        Args:
            features: 音频特征字典
            
        Returns:
            是否有背景音乐
        """
        # 基于经验阈值判断
        # 这些阈值可以根据实际测试结果调整
        
        # 频谱质心变化大通常表示有音乐
        spectral_centroid_std = features["spectral_centroid_std"]
        
        # 频谱带宽变化大表示复杂度高，可能有音乐
        spectral_bandwidth_std = features["spectral_bandwidth_std"]
        
        # MFCC方差大表示音色变化丰富，可能有音乐
        mfcc_variance = features["mfcc_variance"]
        
        # 综合判断
        music_score = (
            min(spectral_centroid_std / 1000, 1.0) * 0.4 +
            min(spectral_bandwidth_std / 1000, 1.0) * 0.3 +
            min(mfcc_variance / 100, 1.0) * 0.3
        )
        
        has_background = music_score > self.quality_threshold
        
        # 更新置信度
        features["confidence"] = music_score
        
        return has_background
    
    def _get_separation_recommendation(self, has_background: bool, features: Dict[str, Any]) -> str:
        """
        获取分离建议
        
        Args:
            has_background: 是否有背景音乐
            features: 音频特征
            
        Returns:
            建议字符串
        """
        if not has_background:
            return "建议直接处理，无需分离"
        
        confidence = features.get("confidence", 0)
        
        if confidence > 0.7:
            return "强烈建议进行音频分离，背景音乐明显"
        elif confidence > 0.4:
            return "建议进行音频分离，可能有背景音乐"
        else:
            return "可选进行音频分离，背景音乐较少"
    
    def _evaluate_separation_quality(self, vocals_path: str, accompaniment_path: str) -> Dict[str, Any]:
        """
        评估分离质量
        
        Args:
            vocals_path: 人声文件路径
            accompaniment_path: 伴奏文件路径
            
        Returns:
            质量评估字典
        """
        try:
            # 加载分离后的音频
            vocals, sr = librosa.load(vocals_path, sr=16000)
            accompaniment, _ = librosa.load(accompaniment_path, sr=16000)
            
            # 计算人声和伴奏的能量比
            vocals_energy = np.sum(vocals ** 2)
            accompaniment_energy = np.sum(accompaniment ** 2)
            
            if accompaniment_energy > 0:
                energy_ratio = vocals_energy / accompaniment_energy
            else:
                energy_ratio = float('inf')
            
            # 计算分离质量分数
            quality_score = min(energy_ratio / 10, 1.0)  # 归一化到0-1
            
            return {
                "quality_score": quality_score,
                "energy_ratio": energy_ratio,
                "vocals_energy": vocals_energy,
                "accompaniment_energy": accompaniment_energy,
                "recommendation": "高质量分离" if quality_score > 0.7 else "分离质量一般"
            }
            
        except Exception as e:
            self.logger.warning(f"分离质量评估失败: {e}")
            return {
                "quality_score": 0.5,
                "energy_ratio": 1.0,
                "recommendation": "无法评估分离质量"
            }
