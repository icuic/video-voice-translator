"""
基于音频的说话者切换检测器
检测音频中的说话者切换点，用于精确的说话者分离
"""

import os
import logging
import numpy as np
import librosa
import soundfile as sf
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from scipy.signal import find_peaks
from .utils import validate_file_path, create_output_dir, safe_filename


class AudioSpeakerDetector:
    """基于音频的说话者切换检测器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化说话者检测器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 检测配置
        self.detection_config = config.get("speaker_detection", {})
        self.window_size = self.detection_config.get("window_size", 0.1)  # 100ms窗口
        self.silence_threshold = self.detection_config.get("silence_threshold", 0.01)
        self.min_silence_duration = self.detection_config.get("min_silence_duration", 0.3)
        self.energy_threshold = self.detection_config.get("energy_threshold", 2.0)
        
    def detect_speaker_changes(self, audio_path: str) -> Dict[str, Any]:
        """
        检测音频中的说话者切换点
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            检测结果字典
        """
        if not validate_file_path(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        self.logger.info(f"开始检测说话者切换: {audio_path}")
        
        try:
            # 加载音频
            audio, sr = librosa.load(audio_path, sr=16000)
            
            # 多种检测方法
            silence_changes = self._detect_silence_changes(audio, sr)
            energy_changes = self._detect_energy_changes(audio, sr)
            spectral_changes = self._detect_spectral_changes(audio, sr)
            
            # 合并检测结果
            all_changes = self._merge_detection_results(
                silence_changes, energy_changes, spectral_changes
            )
            
            # 过滤和优化切换点
            optimized_changes = self._optimize_change_points(all_changes, audio, sr)
            
            result = {
                "success": True,
                "audio_path": audio_path,
                "total_duration": len(audio) / sr,
                "change_points": optimized_changes,
                "detection_methods": {
                    "silence": len(silence_changes),
                    "energy": len(energy_changes),
                    "spectral": len(spectral_changes)
                },
                "processing_info": {
                    "window_size": self.window_size,
                    "silence_threshold": self.silence_threshold,
                    "min_silence_duration": self.min_silence_duration
                }
            }
            
            self.logger.info(f"检测到 {len(optimized_changes)} 个说话者切换点")
            return result
            
        except Exception as e:
            self.logger.error(f"说话者切换检测失败: {e}")
            raise
    
    def segment_by_speaker_changes(self, audio_path: str, change_points: List[float], 
                                 output_dir: str) -> Dict[str, Any]:
        """
        根据说话者切换点切分音频
        
        Args:
            audio_path: 原始音频文件路径
            change_points: 切换点时间列表
            output_dir: 输出目录
            
        Returns:
            切分结果字典
        """
        self.logger.info(f"开始根据切换点切分音频: {audio_path}")
        
        try:
            # 加载音频
            audio, sr = librosa.load(audio_path, sr=16000)
            
            # 创建输出目录
            create_output_dir(output_dir)
            
            # 生成切换点（包含开始和结束）
            all_points = [0.0] + change_points + [len(audio) / sr]
            all_points = sorted(list(set(all_points)))  # 去重并排序
            
            # 切分音频
            segments = []
            input_name = Path(audio_path).stem
            safe_name = safe_filename(input_name)
            
            for i in range(len(all_points) - 1):
                start_time = all_points[i]
                end_time = all_points[i + 1]
                
                # 提取音频片段
                start_sample = int(start_time * sr)
                end_sample = int(end_time * sr)
                segment_audio = audio[start_sample:end_sample]
                
                # 跳过太短的片段
                if len(segment_audio) < sr * 0.5:  # 少于0.5秒
                    continue
                
                # 保存音频片段
                segment_filename = f"{safe_name}_segment_{i:02d}.wav"
                segment_path = os.path.join(output_dir, segment_filename)
                sf.write(segment_path, segment_audio, sr)
                
                segments.append({
                    "segment_id": i,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": end_time - start_time,
                    "audio_path": segment_path,
                    "audio_size": len(segment_audio)
                })
            
            result = {
                "success": True,
                "input_path": audio_path,
                "output_dir": output_dir,
                "segment_count": len(segments),
                "segments": segments,
                "processing_info": {
                    "change_points": change_points,
                    "total_segments": len(segments)
                }
            }
            
            self.logger.info(f"音频切分完成，生成 {len(segments)} 个片段")
            return result
            
        except Exception as e:
            self.logger.error(f"音频切分失败: {e}")
            raise
    
    def _detect_silence_changes(self, audio: np.ndarray, sr: int) -> List[float]:
        """基于静音检测说话者切换"""
        # 计算RMS能量
        frame_length = int(0.025 * sr)  # 25ms帧
        hop_length = int(0.010 * sr)    # 10ms跳跃
        
        rms = []
        for i in range(0, len(audio) - frame_length, hop_length):
            frame = audio[i:i + frame_length]
            rms.append(np.sqrt(np.mean(frame ** 2)))
        
        rms = np.array(rms)
        times = np.arange(len(rms)) * hop_length / sr
        
        # 找到静音段
        silence_mask = rms < self.silence_threshold
        
        # 找到静音段的开始和结束
        silence_starts = []
        silence_ends = []
        
        in_silence = False
        for i, is_silent in enumerate(silence_mask):
            if is_silent and not in_silence:
                silence_starts.append(times[i])
                in_silence = True
            elif not is_silent and in_silence:
                silence_ends.append(times[i])
                in_silence = False
        
        # 过滤掉太短的静音段
        long_silences = []
        for start, end in zip(silence_starts, silence_ends):
            if end - start >= self.min_silence_duration:
                long_silences.append((start, end))
        
        # 返回静音段的中间点作为切换点
        change_points = []
        for start, end in long_silences:
            change_points.append((start + end) / 2)
        
        return change_points
    
    def _detect_energy_changes(self, audio: np.ndarray, sr: int) -> List[float]:
        """基于能量变化检测说话者切换"""
        hop_length = int(self.window_size * sr)
        frame_length = hop_length
        
        # 计算短时能量
        energy = []
        for i in range(0, len(audio) - frame_length, hop_length):
            frame = audio[i:i + frame_length]
            energy.append(np.sum(frame ** 2))
        
        energy = np.array(energy)
        times = np.arange(len(energy)) * self.window_size
        
        # 计算能量变化率
        energy_diff = np.abs(np.diff(energy))
        
        # 找到能量变化较大的点
        threshold = np.mean(energy_diff) + self.energy_threshold * np.std(energy_diff)
        change_indices = find_peaks(energy_diff, height=threshold)[0]
        
        return times[change_indices].tolist()
    
    def _detect_spectral_changes(self, audio: np.ndarray, sr: int) -> List[float]:
        """基于频谱变化检测说话者切换"""
        hop_length = int(self.window_size * sr)
        
        # 计算MFCC特征
        mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13, hop_length=hop_length)
        
        # 计算MFCC变化
        mfcc_diff = np.sum(np.abs(np.diff(mfcc, axis=1)), axis=0)
        
        # 找到变化较大的点
        threshold = np.mean(mfcc_diff) + 1.5 * np.std(mfcc_diff)
        change_indices = find_peaks(mfcc_diff, height=threshold)[0]
        
        times = np.arange(len(mfcc_diff)) * self.window_size
        return times[change_indices].tolist()
    
    def _merge_detection_results(self, silence_changes: List[float], 
                               energy_changes: List[float], 
                               spectral_changes: List[float]) -> List[float]:
        """合并不同检测方法的结果"""
        all_changes = silence_changes + energy_changes + spectral_changes
        
        # 去重并排序
        unique_changes = sorted(list(set(all_changes)))
        
        # 过滤掉太接近的点（小于0.5秒）
        filtered_changes = []
        for change in unique_changes:
            if not filtered_changes or change - filtered_changes[-1] > 0.5:
                filtered_changes.append(change)
        
        return filtered_changes
    
    def _optimize_change_points(self, change_points: List[float], 
                              audio: np.ndarray, sr: int) -> List[float]:
        """优化切换点，确保在合适的音频位置"""
        if not change_points:
            return []
        
        optimized = []
        
        for point in change_points:
            # 在切换点附近寻找更好的切分位置
            search_range = 0.2  # 搜索范围±0.2秒
            start_search = max(0, point - search_range)
            end_search = min(len(audio) / sr, point + search_range)
            
            # 在搜索范围内找到能量最低的点
            best_point = point
            min_energy = float('inf')
            
            search_samples = int(search_range * sr)
            point_sample = int(point * sr)
            start_sample = max(0, point_sample - search_samples)
            end_sample = min(len(audio), point_sample + search_samples)
            
            for i in range(start_sample, end_sample, int(0.01 * sr)):  # 10ms步长
                window = audio[i:i + int(0.1 * sr)]  # 100ms窗口
                if len(window) > 0:
                    energy = np.mean(window ** 2)
                    if energy < min_energy:
                        min_energy = energy
                        best_point = i / sr
            
            optimized.append(best_point)
        
        return optimized

