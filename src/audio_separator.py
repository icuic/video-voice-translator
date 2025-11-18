"""
音频分离器模块
使用Demucs进行人声和背景音乐的分离
"""

import os
import sys
import logging
import numpy as np
import librosa
import subprocess
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
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
        
        # 初始化Demucs分离器
        try:
            # 使用htdemucs模型（更好的分离效果）
            self.model_name = "htdemucs"
            self.logger.info("Demucs分离器初始化成功")
        except Exception as e:
            self.logger.error(f"Demucs初始化失败: {e}")
            raise
        
        # 分离配置 - 提取为类属性，支持配置覆盖
        self.separation_config = config.get("audio_separation", {})
        self.enable_gpu = self.separation_config.get("enable_gpu", True)
        self.quality_threshold = self.separation_config.get("quality_threshold", 0.3)
        
        # 其他可配置参数
        self.spectral_centroid_weight = self.separation_config.get("spectral_centroid_weight", 0.4)
        self.spectral_bandwidth_weight = self.separation_config.get("spectral_bandwidth_weight", 0.3)
        self.mfcc_variance_weight = self.separation_config.get("mfcc_variance_weight", 0.3)
        self.energy_ratio_threshold = self.separation_config.get("energy_ratio_threshold", 10.0)
    
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
    
    
    def separate_audio_with_paths(self, audio_path: str, vocals_path: str, accompaniment_path: str) -> Dict[str, Any]:
        """
        分离音频到指定路径
        
        Args:
            audio_path: 输入音频文件路径
            vocals_path: 人声输出路径
            accompaniment_path: 背景音乐输出路径
            
        Returns:
            分离结果字典
        """
        if not validate_file_path(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        self.logger.info(f"开始音频分离到指定路径: {audio_path}")
        
        # 创建输出目录
        os.makedirs(os.path.dirname(vocals_path), exist_ok=True)
        os.makedirs(os.path.dirname(accompaniment_path), exist_ok=True)
        
        try:
            # 生成临时输出目录
            temp_output_dir = os.path.join(os.path.dirname(vocals_path), "temp_separation")
            os.makedirs(temp_output_dir, exist_ok=True)
            
            # 执行Demucs分离
            input_name = Path(audio_path).stem
            safe_name = safe_filename(input_name)
            self._run_demucs_separation(audio_path, temp_output_dir, safe_name)
            
            # 查找分离后的文件
            # Demucs 生成的目录名可能不是基于输入文件名，需要动态查找
            htdemucs_dir = os.path.join(temp_output_dir, "htdemucs")
            demucs_output_dir = None
            
            # 查找实际的输出目录
            if os.path.exists(htdemucs_dir):
                for item in os.listdir(htdemucs_dir):
                    item_path = os.path.join(htdemucs_dir, item)
                    if os.path.isdir(item_path):
                        # 检查是否包含 vocals.wav 和 no_vocals.wav
                        vocals_file = os.path.join(item_path, "vocals.wav")
                        accompaniment_file = os.path.join(item_path, "no_vocals.wav")
                        if os.path.exists(vocals_file) and os.path.exists(accompaniment_file):
                            demucs_output_dir = item_path
                            break
            
            if demucs_output_dir:
                temp_vocals = os.path.join(demucs_output_dir, "vocals.wav")
                temp_accompaniment = os.path.join(demucs_output_dir, "no_vocals.wav")
            else:
                # 如果htdemucs目录中不存在，检查根目录
                temp_vocals = os.path.join(temp_output_dir, f"{safe_name}_vocals.wav")
                temp_accompaniment = os.path.join(temp_output_dir, f"{safe_name}_accompaniment.wav")
            
            # 验证临时文件
            if not os.path.exists(temp_vocals) or not os.path.exists(temp_accompaniment):
                raise RuntimeError("音频分离失败，临时文件未生成")
            
            # 复制到目标路径
            import shutil
            shutil.copy2(temp_vocals, vocals_path)
            shutil.copy2(temp_accompaniment, accompaniment_path)
            
            # 清理临时目录
            shutil.rmtree(temp_output_dir, ignore_errors=True)
            
            # 获取文件信息
            vocals_size = os.path.getsize(vocals_path)
            accompaniment_size = os.path.getsize(accompaniment_path)
            
            result = {
                "success": True,
                "input_path": audio_path,
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
        
        # 生成输出文件路径
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        vocals_path = os.path.join(output_dir, f"{base_name}_vocals.wav")
        accompaniment_path = os.path.join(output_dir, f"{base_name}_accompaniment.wav")
        
        # 执行分离
        result = self.separate_audio_with_paths(audio_path, vocals_path, accompaniment_path)
        
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
        
        # 综合判断 - 使用配置参数
        music_score = (
            min(spectral_centroid_std / 1000, 1.0) * self.spectral_centroid_weight +
            min(spectral_bandwidth_std / 1000, 1.0) * self.spectral_bandwidth_weight +
            min(mfcc_variance / 100, 1.0) * self.mfcc_variance_weight
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
            
            # 计算分离质量分数 - 使用配置参数
            quality_score = min(energy_ratio / self.energy_ratio_threshold, 1.0)  # 归一化到0-1
            
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
    
    def _run_demucs_separation(self, audio_path: str, output_dir: str, safe_name: str):
        """
        运行Demucs分离
        
        Args:
            audio_path: 输入音频文件路径
            output_dir: 输出目录
            safe_name: 安全的文件名
        """
        try:
            # 清理GPU缓存，为Demucs释放内存
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                self.logger.info("已清理GPU缓存，为Demucs释放内存")
            
            # 构建Demucs命令 - 使用当前Python解释器
            cmd = [
                sys.executable, "-m", "demucs",
                "--two-stems", "vocals",
                "-o", output_dir,
                audio_path
            ]
            
            self.logger.info(f"执行Demucs分离: {' '.join(cmd)}")
            self.logger.info("提示: 如果是首次运行，Demucs 需要下载模型（约80MB），请耐心等待...")
            
            # 使用 Popen 实时读取输出，让用户能看到下载进度
            # 设置环境变量确保输出不被缓冲
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
                text=True,
                bufsize=0,  # 无缓冲，确保实时输出
                universal_newlines=True,
                env=env
            )
            
            # 实时读取并记录输出
            output_lines = []
            last_log_time = 0
            
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    # 清理 ANSI 转义码（进度条可能使用）
                    clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)  # 移除 ANSI 颜色码
                    clean_line = re.sub(r'\r', '', clean_line)  # 移除回车符
                    
                    if clean_line.strip():
                        # 对于进度条，每0.5秒记录一次，避免日志过多
                        current_time = time.time()
                        if 'Downloading' in clean_line or '%' in clean_line or '|' in clean_line:
                            if current_time - last_log_time > 0.5:
                                self.logger.info(f"Demucs: {clean_line}")
                                last_log_time = current_time
                        else:
                            # 普通输出立即记录
                            self.logger.info(f"Demucs: {clean_line}")
                            last_log_time = current_time
                        
                        output_lines.append(clean_line)
            
            # 等待进程完成
            return_code = process.wait()
            
            if return_code != 0:
                error_msg = "\n".join(output_lines[-20:])  # 只显示最后20行错误信息
                self.logger.error(f"Demucs分离失败，退出码: {return_code}")
                self.logger.error(f"错误输出: {error_msg}")
                raise RuntimeError(f"Demucs分离失败: {error_msg}")
            
            self.logger.info("Demucs分离完成")
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Demucs分离失败: {e}")
            if hasattr(e, 'stderr') and e.stderr:
                self.logger.error(f"错误输出: {e.stderr}")
            raise RuntimeError(f"Demucs分离失败: {e}")
        except Exception as e:
            self.logger.error(f"Demucs分离过程中出现异常: {e}")
            raise
    
    def clear_gpu_cache(self):
        """
        清理GPU缓存
        """
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                self.logger.info("GPU缓存清理完成")
        except Exception as e:
            self.logger.warning(f"GPU缓存清理失败: {e}")
