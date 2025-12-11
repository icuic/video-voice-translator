"""
时间同步音频合并器
用于将翻译后的音频片段按正确的时间戳合并到完整的音频轨道中
"""

import os
import subprocess
import tempfile
import logging
from typing import List, Dict, Any, Optional
import numpy as np
import librosa
import soundfile as sf
from .output_manager import OutputManager, StepNumbers


class TimestampedAudioMerger:
    """时间同步音频合并器类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化时间同步音频合并器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 音频参数
        self.sample_rate = config.get("audio", {}).get("sample_rate", 44100)
        self.audio_format = config.get("audio", {}).get("format", "wav")
        
        # 时长控制参数
        self.max_speed_ratio = 2.0  # 最大允许倍速（2.0倍速，超过此倍速则裁剪）
        
        self.logger.info("时间同步音频合并器初始化完成")
    
    def _recalculate_segment_timestamps(self, segments: List[Dict[str, Any]], total_duration: float) -> List[Dict[str, Any]]:
        """
        重新计算分段时间戳，基于实际音频时长，但保持原始视频总时长
        
        Args:
            segments: 原始分段列表
            total_duration: 原始视频总时长
            
        Returns:
            重新计算时间戳后的分段列表
        """
        self.logger.info("🔄 重新计算分段时间戳，基于实际音频时长，保持原始视频总时长...")
        
        # 收集所有有效的音频文件
        valid_segments = []
        total_audio_duration = 0.0
        
        for i, segment in enumerate(segments):
            audio_path = segment.get("audio_path", "")
            
            if not audio_path or not os.path.exists(audio_path):
                self.logger.warning(f"分段 {i} 音频文件不存在，跳过: {audio_path}")
                continue
            
            # 获取实际音频时长
            actual_duration = self.get_original_audio_duration(audio_path)
            
            if actual_duration <= 0:
                self.logger.warning(f"分段 {i} 无法获取音频时长，跳过")
                continue
            
            valid_segments.append((i, segment, actual_duration))
            total_audio_duration += actual_duration
        
        if not valid_segments:
            self.logger.error("没有有效的音频分段")
            return segments
        
        # 计算时间分配策略
        if total_audio_duration <= total_duration:
            # 如果总音频时长 <= 视频时长，直接按顺序分配
            self.logger.info(f"总音频时长 ({total_audio_duration:.2f}s) <= 视频时长 ({total_duration:.2f}s)，直接按顺序分配")
            recalculated_segments = []
            current_time = 0.0
            
            for i, segment, actual_duration in valid_segments:
                new_segment = segment.copy()
                new_segment['start'] = current_time
                new_segment['end'] = current_time + actual_duration
                
                self.logger.info(f"分段 {i}: {segment.get('start', 0):.2f}s-{segment.get('end', 0):.2f}s -> {current_time:.2f}s-{current_time + actual_duration:.2f}s (实际音频: {actual_duration:.3f}s)")
                
                recalculated_segments.append(new_segment)
                current_time += actual_duration
            
            # 如果还有剩余时间，用静音填充
            if current_time < total_duration:
                self.logger.info(f"剩余时间: {total_duration - current_time:.2f}s，将在末尾用静音填充")
        else:
            # 如果总音频时长 > 视频时长，需要压缩
            compression_ratio = total_duration / total_audio_duration
            self.logger.warning(f"总音频时长 ({total_audio_duration:.2f}s) > 视频时长 ({total_duration:.2f}s)，需要压缩 {compression_ratio:.2f} 倍")
            
            recalculated_segments = []
            current_time = 0.0
            
            for i, segment, actual_duration in valid_segments:
                compressed_duration = actual_duration * compression_ratio
                new_segment = segment.copy()
                new_segment['start'] = current_time
                new_segment['end'] = current_time + compressed_duration
                
                self.logger.info(f"分段 {i}: {segment.get('start', 0):.2f}s-{segment.get('end', 0):.2f}s -> {current_time:.2f}s-{current_time + compressed_duration:.2f}s (压缩: {actual_duration:.3f}s -> {compressed_duration:.3f}s)")
                
                recalculated_segments.append(new_segment)
                current_time += compressed_duration
        
        self.logger.info(f"✅ 时间戳重新计算完成，总时长: {total_duration:.2f}s")
        
        return recalculated_segments
    
    def create_timestamped_audio_track(self, segments: List[Dict[str, Any]], 
                                     total_duration: float, 
                                     output_path: str) -> Dict[str, Any]:
        """
        创建时间同步的音频轨道
        
        Args:
            segments: 包含时间戳和音频文件路径的片段列表
            total_duration: 原始音频的总时长
            output_path: 输出文件路径
            
        Returns:
            合并结果字典
        """
        self.logger.info(f"开始创建时间同步音频轨道，总时长: {total_duration:.2f}秒")
        
        # 保持原始分段时间戳不变，只修复倍速处理
        # segments = self._recalculate_segment_timestamps(segments, total_duration)
        
        try:
            # 方法1：使用FFmpeg创建时间同步音频轨道
            # 优先使用librosa方法，因为它在音量保持方面更好
            self.logger.info("使用librosa方法进行音频合并（更好的音量保持）")
            return self._create_with_librosa(segments, total_duration, output_path)
                
        except Exception as e:
            self.logger.error(f"创建时间同步音频轨道失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "output_path": output_path
            }
    
    def create_timestamped_audio_track_with_output_manager(self, segments: List[Dict[str, Any]], 
                                                          total_duration: float, 
                                                          output_manager: OutputManager) -> Dict[str, Any]:
        """
        使用OutputManager创建时间同步的音频轨道
        
        Args:
            segments: 包含时间戳和音频文件路径的片段列表
            total_duration: 原始音频的总时长
            output_manager: 输出管理器实例
            
        Returns:
            合并结果字典
        """
        self.logger.info(f"开始创建时间同步音频轨道，总时长: {total_duration:.2f}秒")
        output_manager.log(f"步骤8开始: 音频合并，总时长 {total_duration:.2f}秒")
        
        try:
            # 使用OutputManager生成输出文件路径
            output_path = output_manager.get_file_path(StepNumbers.STEP_8, "final_voice")
            
            # 使用librosa方法进行音频合并
            self.logger.info("使用librosa方法进行音频合并（更好的音量保持）")
            result = self._create_with_librosa(segments, total_duration, output_path)
            
            if result["success"]:
                output_manager.log(f"步骤8完成: 音频合并完成，输出文件: {output_path}")
                # 更新结果中的文件路径
                result["output_path"] = output_path
            else:
                output_manager.log(f"步骤8失败: {result.get('error', '未知错误')}")
            
            return result
                
        except Exception as e:
            self.logger.error(f"创建时间同步音频轨道失败: {e}")
            output_manager.log(f"步骤8失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "output_path": output_manager.get_file_path(8, "final_voice") if output_manager else None
            }
    
    def _create_with_ffmpeg(self, segments: List[Dict[str, Any]], 
                           total_duration: float, 
                           output_path: str) -> Dict[str, Any]:
        """
        使用FFmpeg创建时间同步音频轨道
        
        Args:
            segments: 片段列表
            total_duration: 总时长
            output_path: 输出路径
            
        Returns:
            处理结果
        """
        try:
            # 创建临时目录
            temp_dir = tempfile.mkdtemp()
            
            # 1. 创建静音轨道作为基础
            silent_audio = os.path.join(temp_dir, "silent.wav")
            self._create_silent_audio(total_duration, silent_audio)
            
            # 2. 为每个片段创建带时长控制的音频
            segment_files = []
            for i, segment in enumerate(segments):
                start_time = segment.get("start", 0.0)
                end_time = segment.get("end", 0.0)
                target_duration = end_time - start_time
                audio_file = segment.get("audio_path", "")
                
                if not audio_file or not os.path.exists(audio_file):
                    self.logger.warning(f"片段 {i} 的音频文件不存在: {audio_file}")
                    continue
                
                # 检查并调整音频时长
                adjusted_audio = os.path.join(temp_dir, f"segment_{i:03d}_adjusted.wav")
                duration_adjusted = self._adjust_audio_duration_if_needed(
                    audio_file, target_duration, adjusted_audio
                )
                
                if duration_adjusted:
                    # 创建带延迟的音频文件
                    delayed_audio = os.path.join(temp_dir, f"segment_{i:03d}_delayed.wav")
                    self._add_delay_to_audio(adjusted_audio, start_time, delayed_audio)
                    segment_files.append(delayed_audio)
                else:
                    self.logger.warning(f"片段 {i} 音频时长调整失败，跳过")
            
            # 3. 合并所有音频
            if segment_files:
                self._merge_audio_files([silent_audio] + segment_files, output_path)
            else:
                # 如果没有有效片段，直接复制静音文件
                import shutil
                shutil.copy2(silent_audio, output_path)
            
            # 清理临时文件
            import shutil
            shutil.rmtree(temp_dir)
            
            return {
                "success": True,
                "output_path": output_path,
                "segments_processed": len(segment_files),
                "total_duration": total_duration,
                "method": "ffmpeg"
            }
            
        except Exception as e:
            self.logger.error(f"FFmpeg方法失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "method": "ffmpeg"
            }
    
    def _create_with_librosa(self, segments: List[Dict[str, Any]], 
                            total_duration: float, 
                            output_path: str) -> Dict[str, Any]:
        """
        使用librosa创建时间同步音频轨道
        
        Args:
            segments: 片段列表
            total_duration: 总时长
            output_path: 输出路径
            
        Returns:
            处理结果
        """
        try:
            # 优化采样率选择策略：检测克隆音频和背景音乐的采样率，选择较高的作为目标采样率
            # 先找到第一个有效的音频文件，加载它来获取原始采样率
            detected_sample_rate = None
            first_valid_audio_file = None
            
            for segment in segments:
                audio_file = segment.get("audio_path", "")
                if audio_file and os.path.exists(audio_file):
                    first_valid_audio_file = audio_file
                    break
            
            if first_valid_audio_file:
                # 加载第一个分段（不指定采样率），自动获取原始采样率
                try:
                    _, detected_sample_rate = librosa.load(first_valid_audio_file, sr=None)
                    self.logger.info(f"🎵 检测到克隆音频采样率: {detected_sample_rate} Hz")
                except Exception as e:
                    self.logger.warning(f"无法检测采样率，使用配置的采样率: {e}")
                    detected_sample_rate = self.sample_rate
            else:
                self.logger.warning("未找到有效的音频文件，使用配置的采样率")
                detected_sample_rate = self.sample_rate
            
            # 检查背景音乐的采样率（如果存在）
            output_dir = os.path.dirname(output_path)
            accompaniment_path = os.path.join(output_dir, "02_accompaniment.wav")
            accompaniment_sample_rate = None
            if os.path.exists(accompaniment_path):
                try:
                    _, accompaniment_sample_rate = librosa.load(accompaniment_path, sr=None)
                    self.logger.info(f"🎵 检测到背景音乐采样率: {accompaniment_sample_rate} Hz")
                except Exception as e:
                    self.logger.warning(f"无法检测背景音乐采样率: {e}")
            
            # 选择两者中较高的采样率作为目标采样率（避免降采样导致音质损失）
            if accompaniment_sample_rate is not None:
                actual_sample_rate = max(detected_sample_rate, accompaniment_sample_rate)
                if actual_sample_rate != detected_sample_rate:
                    self.logger.info(f"📊 选择较高采样率: {actual_sample_rate} Hz（背景音乐 {accompaniment_sample_rate} Hz > 克隆音频 {detected_sample_rate} Hz），将升采样克隆音频而非降采样背景音乐")
                else:
                    self.logger.info(f"📊 选择较高采样率: {actual_sample_rate} Hz（克隆音频 {detected_sample_rate} Hz >= 背景音乐 {accompaniment_sample_rate} Hz）")
            else:
                actual_sample_rate = detected_sample_rate
                self.logger.info(f"📊 使用采样率: {actual_sample_rate} Hz 进行音频合并（无背景音乐）")
            
            # 计算总样本数（使用检测到的采样率）
            total_samples = int(total_duration * actual_sample_rate)
            
            # 创建静音轨道
            audio_track = np.zeros(total_samples, dtype=np.float32)
            
            # 创建临时目录用于存储调整后的音频
            import tempfile
            temp_dir = tempfile.mkdtemp()
            
            # 处理每个片段
            segments_processed = 0
            for i, segment in enumerate(segments):
                start_time = segment.get("start", 0.0)
                end_time = segment.get("end", 0.0)
                audio_file = segment.get("audio_path", "")
                
                # 添加详细调试信息
                self.logger.info(f"🔍 处理分段 {i}:")
                self.logger.info(f"  时间戳: {start_time:.2f}s - {end_time:.2f}s")
                self.logger.info(f"  分段时长: {end_time - start_time:.2f}s")
                self.logger.info(f"  音频文件: {audio_file}")
                
                if not audio_file or not os.path.exists(audio_file):
                    self.logger.warning(f"片段 {i} 的音频文件不存在: {audio_file}")
                    continue
                
                try:
                    # 检查并调整音频时长
                    target_duration = end_time - start_time
                    adjusted_audio = os.path.join(temp_dir, f"segment_{i:03d}_adjusted.wav")
                    duration_adjusted = self._adjust_audio_duration_if_needed(
                        audio_file, target_duration, adjusted_audio
                    )
                    
                    # 使用调整后的音频文件（如果调整成功）或原始文件
                    final_audio_file = adjusted_audio if duration_adjusted else audio_file
                    
                    # 加载音频文件（使用 sr=None 保持原始采样率，如果采样率不一致则重采样到检测到的采样率）
                    audio_data, sr = librosa.load(final_audio_file, sr=None)
                    
                    # 如果采样率不一致，重采样到目标采样率（使用高质量重采样算法）
                    if sr != actual_sample_rate:
                        if sr < actual_sample_rate:
                            self.logger.info(f"  🔄 采样率不匹配 ({sr} Hz < {actual_sample_rate} Hz)，升采样到 {actual_sample_rate} Hz（使用kaiser_best算法）")
                        else:
                            self.logger.info(f"  🔄 采样率不匹配 ({sr} Hz > {actual_sample_rate} Hz)，降采样到 {actual_sample_rate} Hz（使用kaiser_best算法）")
                        audio_data = librosa.resample(audio_data, orig_sr=sr, target_sr=actual_sample_rate, res_type='kaiser_best')
                        sr = actual_sample_rate
                    # 使用检测到的采样率计算时长（此时 sr 应该等于 actual_sample_rate）
                    actual_audio_duration = len(audio_data) / actual_sample_rate
                    
                    # 添加音频文件信息
                    self.logger.info(f"  实际音频时长: {actual_audio_duration:.3f}s")
                    self.logger.info(f"  分段目标时长: {end_time - start_time:.3f}s")
                    self.logger.info(f"  时长差异: {actual_audio_duration - (end_time - start_time):+.3f}s")
                    
                    # 计算插入位置和时间窗口（使用检测到的采样率）
                    start_sample = int(start_time * actual_sample_rate)
                    
                    # 使用实际音频时长而不是原始分段时间戳
                    actual_audio_duration_samples = len(audio_data)
                    end_sample = start_sample + actual_audio_duration_samples
                    target_duration_samples = actual_audio_duration_samples
                    
                    # 添加时间窗口信息
                    self.logger.info(f"  时间窗口: {start_sample} - {end_sample} 样本")
                    self.logger.info(f"  目标时长样本数: {target_duration_samples}")
                    self.logger.info(f"  实际音频样本数: {len(audio_data)}")
                    
                    # 确保不超出总时长边界
                    if end_sample > total_samples:
                        end_sample = total_samples
                        actual_audio_duration_samples = end_sample - start_sample
                        padded_audio = audio_data[:actual_audio_duration_samples]
                        self.logger.warning(f"  ⚠️ 分段超出总时长，裁剪到: {actual_audio_duration_samples/actual_sample_rate:.3f}s")
                    else:
                        # 直接使用实际音频，不需要填充或扩展
                        padded_audio = audio_data
                        self.logger.info(f"  ✅ 直接使用实际音频: {len(audio_data)/actual_sample_rate:.3f}s")
                    
                    # 对所有音频片段应用末尾淡出，消除数字伪影（额外保护）
                    fade_out_duration = 0.02  # 20ms淡出
                    fade_out_samples = int(fade_out_duration * actual_sample_rate)
                    if len(padded_audio) > fade_out_samples:
                        fade_out_start = len(padded_audio) - fade_out_samples
                        fade_curve = np.linspace(1.0, 0.0, fade_out_samples)
                        padded_audio[fade_out_start:] *= fade_curve
                        self.logger.info(f"  ✅ 已应用末尾淡出: {fade_out_duration*1000:.0f}ms")
                    
                    # 检查是否与之前的音频重叠
                    if start_sample < len(audio_track):
                        existing_audio = audio_track[start_sample:end_sample]
                        has_existing = np.any(np.abs(existing_audio) > 1e-6)
                        
                        if has_existing:
                            # 存在重叠，使用全局优化策略
                            self.logger.warning(f"  ⚠️ 检测到音频重叠，使用全局优化策略")
                            
                            # 计算重叠时长（使用检测到的采样率）
                            overlap_duration = (start_sample - len(audio_track)) / actual_sample_rate if start_sample < len(audio_track) else 0
                            
                            if overlap_duration > 0:
                                # 全局优化策略：最小化调整距离和调整数量
                                adjustment_success = False
                                
                                # 计算当前分段的原始起始时间（用于计算偏差）
                                current_segment_start_time = start_time
                                
                                # 方案1：尝试最小化当前分段的移动距离
                                # 向前移动：保持与原始起始点最近
                                if start_sample > 0:
                                    # 计算最小必要移动距离（刚好消除重叠）
                                    min_shift = overlap_duration * actual_sample_rate * 1.1  # 多移动10%确保安全
                                    optimal_shift = min(min_shift, start_sample)
                                    new_start_sample = max(0, start_sample - int(optimal_shift))
                                    new_end_sample = new_start_sample + len(padded_audio)
                                    
                                    # 检查新位置是否安全且不会影响其他分段
                                    if (new_start_sample < len(audio_track) and 
                                        new_end_sample <= total_samples and
                                        self._is_position_safe(audio_track, new_start_sample, new_end_sample)):
                                        
                                        # 计算移动后的时间偏差
                                        new_start_time = new_start_sample / actual_sample_rate
                                        time_deviation = abs(new_start_time - current_segment_start_time)
                                        
                                        # 如果偏差在可接受范围内（比如0.5秒），使用新位置
                                        if time_deviation <= 0.5:
                                            audio_track[new_start_sample:new_end_sample] = padded_audio
                                            self.logger.info(f"  ✅ 全局优化成功: 向前移动 {optimal_shift/actual_sample_rate:.3f}s，时间偏差 {time_deviation:.3f}s，新位置 {new_start_sample}-{new_end_sample}")
                                            adjustment_success = True
                                
                                # 方案2：如果向前移动偏差太大，尝试向后移动
                                if not adjustment_success and end_sample < total_samples:
                                    # 计算最小必要移动距离
                                    min_shift = overlap_duration * actual_sample_rate * 1.1
                                    new_start_sample = start_sample + int(min_shift)
                                    new_end_sample = new_start_sample + len(padded_audio)
                                    
                                    # 检查新位置是否安全
                                    if (new_end_sample <= total_samples and
                                        self._is_position_safe(audio_track, new_start_sample, new_end_sample)):
                                        
                                        # 计算移动后的时间偏差
                                        new_start_time = new_start_sample / actual_sample_rate
                                        time_deviation = abs(new_start_time - current_segment_start_time)
                                        
                                        # 如果偏差在可接受范围内，使用新位置
                                        if time_deviation <= 0.5:
                                            audio_track[new_start_sample:new_end_sample] = padded_audio
                                            self.logger.info(f"  ✅ 全局优化成功: 向后移动 {min_shift/actual_sample_rate:.3f}s，时间偏差 {time_deviation:.3f}s，新位置 {new_start_sample}-{new_end_sample}")
                                            adjustment_success = True
                                
                                # 方案3：如果全局优化失败，使用音频混合
                                if not adjustment_success:
                                    mixed_audio = (audio_track[start_sample:end_sample] + padded_audio) * 0.5
                                    audio_track[start_sample:end_sample] = mixed_audio
                                    self.logger.info(f"  ✅ 全局优化失败，使用音频混合: 位置 {start_sample}-{end_sample}")
                            else:
                                # 没有重叠时长，直接混合
                                mixed_audio = (audio_track[start_sample:end_sample] + padded_audio) * 0.5
                                audio_track[start_sample:end_sample] = mixed_audio
                                self.logger.info(f"  ✅ 音频混合成功: 位置 {start_sample}-{end_sample}")
                        else:
                            # 没有重叠，直接插入
                            audio_track[start_sample:end_sample] = padded_audio
                            self.logger.info(f"  ✅ 音频插入成功: 位置 {start_sample}-{end_sample}")
                    else:
                        # 超出总时长，直接插入
                        if end_sample <= total_samples:
                            audio_track[start_sample:end_sample] = padded_audio
                            self.logger.info(f"  ✅ 音频插入成功: 位置 {start_sample}-{end_sample}")
                        else:
                            self.logger.warning(f"  ❌ 开始位置超出总时长: {start_sample} >= {total_samples}")
                            continue
                    
                    segments_processed += 1
                        
                except Exception as e:
                    self.logger.warning(f"处理片段 {i} 失败: {e}")
                    continue
            
            # 检查是否存在背景音乐文件，如果存在则合并
            # 使用新的标准化命名规则
            output_dir = os.path.dirname(output_path)
            accompaniment_path = os.path.join(output_dir, "02_accompaniment.wav")
            if os.path.exists(accompaniment_path):
                self.logger.info(f"🎵 发现背景音乐文件，开始合并: {accompaniment_path}")
                try:
                    # 加载背景音乐（使用检测到的采样率）
                    accompaniment_data, accomp_sr = librosa.load(accompaniment_path, sr=None)
                    
                    # 如果采样率不一致，重采样到目标采样率（使用高质量重采样算法）
                    if accomp_sr != actual_sample_rate:
                        if accomp_sr < actual_sample_rate:
                            self.logger.info(f"  🔄 背景音乐采样率不匹配 ({accomp_sr} Hz < {actual_sample_rate} Hz)，升采样到 {actual_sample_rate} Hz（使用kaiser_best算法）")
                        else:
                            self.logger.info(f"  🔄 背景音乐采样率不匹配 ({accomp_sr} Hz > {actual_sample_rate} Hz)，降采样到 {actual_sample_rate} Hz（使用kaiser_best算法）")
                        accompaniment_data = librosa.resample(accompaniment_data, orig_sr=accomp_sr, target_sr=actual_sample_rate, res_type='kaiser_best')
                        accomp_sr = actual_sample_rate
                    
                    # 调整背景音乐长度以匹配语音轨道
                    if len(accompaniment_data) < len(audio_track):
                        # 背景音乐较短，填充静音
                        padding = np.zeros(len(audio_track) - len(accompaniment_data))
                        accompaniment_data = np.concatenate([accompaniment_data, padding])
                    elif len(accompaniment_data) > len(audio_track):
                        # 背景音乐较长，裁剪
                        accompaniment_data = accompaniment_data[:len(audio_track)]
                    
                    # 分析原始音频中背景音乐和人声的相对比例
                    original_voice_rms, original_accomp_rms = self._analyze_original_audio_ratio(output_dir, actual_sample_rate)
                    
                    # 优化处理顺序：先进行音量平衡，再进行混合，最后统一进行音量标准化
                    # 合并语音和背景音乐，并进行音量平衡（保持原始比例）
                    final_audio = self._balance_audio_levels(audio_track, accompaniment_data, 
                                                             original_voice_rms, original_accomp_rms)
                    self.logger.info("✅ 背景音乐合并成功")
                    
                    # 音量标准化（最后统一进行）
                    final_audio_normalized = self._normalize_audio_volume(final_audio)
                    
                    # 保存合并后的音频（使用检测到的采样率）
                    # soundfile会自动将float32转换为PCM_16，并使用高质量dithering减少量化误差
                    # 使用PCM_16格式（最通用，soundfile会自动进行高质量转换）
                    sf.write(output_path, final_audio_normalized, actual_sample_rate, subtype='PCM_16')
                except Exception as e:
                    self.logger.warning(f"背景音乐合并失败: {e}，仅保存语音")
                    # 如果合并失败，先进行音量标准化，然后保存原始语音（使用检测到的采样率）
                    audio_track_normalized = self._normalize_audio_volume(audio_track)
                    sf.write(output_path, audio_track_normalized, actual_sample_rate, subtype='PCM_16')
            else:
                self.logger.info("⚠️  未找到背景音乐文件，仅保存语音")
                # 优化处理顺序：最后统一进行音量标准化
                final_audio_normalized = self._normalize_audio_volume(audio_track)
                # 保存最终音频（使用检测到的采样率）
                # soundfile会自动将float32转换为PCM_16，并使用高质量dithering减少量化误差
                sf.write(output_path, final_audio_normalized, actual_sample_rate, subtype='PCM_16')
            
            # 清理临时目录
            import shutil
            shutil.rmtree(temp_dir)
            
            return {
                "success": True,
                "output_path": output_path,
                "segments_processed": segments_processed,
                "total_duration": total_duration,
                "method": "librosa"
            }
            
        except Exception as e:
            self.logger.error(f"librosa方法失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "method": "librosa"
            }
    
    def _create_silent_audio(self, duration: float, output_path: str):
        """
        创建静音音频文件
        
        Args:
            duration: 时长（秒）
            output_path: 输出路径
        """
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f'anullsrc=channel_layout=stereo:sample_rate={self.sample_rate}',
            '-t', str(duration),
            '-y',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"创建静音音频失败: {result.stderr}")
    
    def _add_delay_to_audio(self, input_audio: str, delay_seconds: float, output_audio: str):
        """
        为音频添加延迟
        
        Args:
            input_audio: 输入音频文件
            delay_seconds: 延迟秒数
            output_audio: 输出音频文件
        """
        if delay_seconds <= 0:
            # 不需要延迟，直接复制
            import shutil
            shutil.copy2(input_audio, output_audio)
            return
        
        cmd = [
            'ffmpeg',
            '-i', input_audio,
            '-af', f'adelay={int(delay_seconds * 1000)}',
            '-y',
            output_audio
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"添加延迟失败: {result.stderr}")
    
    def _is_position_safe(self, audio_track: np.ndarray, start_sample: int, end_sample: int) -> bool:
        """
        检查指定位置是否安全（没有与其他音频重叠）
        
        Args:
            audio_track: 音频轨道
            start_sample: 开始样本位置
            end_sample: 结束样本位置
            
        Returns:
            是否安全
        """
        try:
            # 检查边界
            if start_sample < 0 or end_sample > len(audio_track):
                return False
            
            # 检查是否有现有音频
            existing_audio = audio_track[start_sample:end_sample]
            has_existing = np.any(np.abs(existing_audio) > 1e-6)
            
            return not has_existing
        except Exception:
            return False
    
    def _merge_audio_files(self, audio_files: List[str], output_path: str):
        """
        合并多个音频文件（时间同步混合）
        
        Args:
            audio_files: 音频文件列表 [静音轨道, 分段1, 分段2, ...]
            output_path: 输出路径
        """
        if len(audio_files) == 1:
            # 只有一个文件，直接复制
            import shutil
            shutil.copy2(audio_files[0], output_path)
            return
        
        # 分析原始参考音频的音量（使用第一个非静音文件作为参考）
        reference_volume = self._analyze_audio_volume(audio_files[1]) if len(audio_files) > 1 else -11.0
        self.logger.info(f"参考音频音量: {reference_volume:.2f} dB")
        
        # 基于观察，合成音频的典型音量约为-24.5dB，需要调整到与参考音频相同
        # 计算音量调整值，让输出音频与参考音频音量接近
        # 额外增加3dB增益，让人声音量更明显
        voice_gain_db = 3.0  # 额外增加3dB音量
        target_volume = reference_volume + voice_gain_db  # 目标音量比参考音频大3dB
        current_volume = -24.5  # 合成音频的典型音量（基于观察）
        volume_adjustment = target_volume - current_volume
        self.logger.info(f"音量调整计算: 目标={target_volume:.2f}dB (参考={reference_volume:.2f}dB + 增益={voice_gain_db}dB), 当前={current_volume:.2f}dB, 调整={volume_adjustment:.2f}dB")
        
        # 构建FFmpeg命令，使用amix进行时间同步混合
        cmd = ['ffmpeg']
        
        # 添加所有输入文件
        for audio_file in audio_files:
            cmd.extend(['-i', audio_file])
        
        # 构建amix滤镜，添加音量标准化
        # 第一个输入是静音轨道，后续是各个分段
        amix_inputs = len(audio_files)
        
        # 使用更简单的音量匹配方法
        # 先分析参考音频音量，然后调整其他音频
        if amix_inputs > 1:
            # 构建音量匹配滤镜
            filter_parts = []
            
            # 为每个音频输入添加音量调整（跳过静音轨道）
            for i in range(1, amix_inputs):
                # 使用volume滤镜进行音量调整
                filter_parts.append(f"[{i}]volume={volume_adjustment}dB[{i}_vol]")
            
            # 构建amix输入
            amix_inputs_list = ["[0]"]  # 静音轨道
            for i in range(1, amix_inputs):
                amix_inputs_list.append(f"[{i}_vol]")
            
            # FFmpeg 4.2.7不支持normalize参数，使用weights来保持音量
            # 给所有音频片段相同的权重，避免音量降低
            weights = " ".join(["1"] * amix_inputs)
            filter_complex = f"{';'.join(filter_parts)};{''.join(amix_inputs_list)}amix=inputs={amix_inputs}:duration=longest:weights=\"{weights}\""
        else:
            filter_complex = f"amix=inputs={amix_inputs}:duration=longest"
        
        cmd.extend([
            '-filter_complex', filter_complex,
            '-y',
            output_path
        ])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception(f"合并音频失败: {result.stderr}")
        
        # 验证输出音频音量
        output_volume = self._analyze_audio_volume(output_path)
        self.logger.info(f"输出音频音量: {output_volume:.2f} dB")
    
    def _analyze_audio_volume(self, audio_path: str) -> float:
        """
        分析音频文件的音量（RMS）
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            音量值（dB）
        """
        try:
            # 使用FFmpeg分析音频音量
            cmd = [
                'ffmpeg',
                '-i', audio_path,
                '-af', 'volumedetect',
                '-f', 'null',
                '-'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # 解析FFmpeg输出中的音量信息
            lines = result.stderr.split('\n')
            for line in lines:
                if 'mean_volume:' in line:
                    # 提取音量值，格式如：mean_volume: -20.5 dB
                    parts = line.split('mean_volume:')
                    if len(parts) > 1:
                        volume_str = parts[1].strip().split()[0]
                        return float(volume_str)
            
            # 如果无法解析，返回默认值
            self.logger.warning(f"无法解析音频音量: {audio_path}")
            return -20.0
            
        except Exception as e:
            self.logger.error(f"分析音频音量失败: {e}")
            return -20.0
    
    def get_original_audio_duration(self, audio_path: str) -> float:
        """
        获取原始音频的时长
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            音频时长（秒）
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'csv=p=0',
                audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                raise Exception(f"获取音频时长失败: {result.stderr}")
                
        except Exception as e:
            self.logger.error(f"获取音频时长失败: {e}")
            return 0.0
    
    def _adjust_audio_duration_if_needed(self, audio_path: str, target_duration: float, output_path: str) -> bool:
        """
        如果翻译后音频时长大于目标时长，压缩至目标时长
        如果小于或等于，保持不变
        添加压缩比例限制，避免语速过快
        """
        try:
            # 获取音频实际时长
            actual_duration = self.get_original_audio_duration(audio_path)
            
            # 添加详细调试信息
            self.logger.info(f"🔍 音频时长调整分析:")
            self.logger.info(f"  音频文件: {audio_path}")
            self.logger.info(f"  实际时长: {actual_duration:.3f}s")
            self.logger.info(f"  目标时长: {target_duration:.3f}s")
            self.logger.info(f"  时长差异: {actual_duration - target_duration:+.3f}s")
            
            if actual_duration <= 0:
                self.logger.warning(f"无法获取音频时长: {audio_path}")
                return False
            
            # 如果实际时长 <= 目标时长，应用淡出效果后复制（消除数字伪影）
            if actual_duration <= target_duration:
                # 对所有音频都应用末尾淡出，消除数字伪影
                fade_out_duration = 0.02  # 20ms淡出
                fade_start_time = max(0, actual_duration - fade_out_duration)
                
                # 使用FFmpeg添加淡出效果
                import tempfile
                temp_dir = tempfile.mkdtemp()
                try:
                    final_output = os.path.join(temp_dir, "final_with_fade.wav")
                    cmd_fade = [
                        'ffmpeg',
                        '-i', audio_path,
                        '-af', f'afade=t=out:st={fade_start_time:.3f}:d={fade_out_duration:.3f}',
                        '-y', final_output
                    ]
                    
                    result_fade = subprocess.run(cmd_fade, capture_output=True, text=True)
                    
                    if result_fade.returncode == 0:
                        import shutil
                        shutil.copy2(final_output, output_path)
                        self.logger.info(f"音频时长合适 ({actual_duration:.2f}s <= {target_duration:.2f}s)，已应用末尾淡出: {fade_out_duration*1000:.0f}ms")
                    else:
                        # 如果淡出处理失败，直接复制（降级处理）
                        self.logger.warning(f"淡出处理失败，直接复制: {result_fade.stderr}")
                        import shutil
                        shutil.copy2(audio_path, output_path)
                    
                    # 清理临时文件
                    import shutil
                    shutil.rmtree(temp_dir)
                    return True
                except Exception as e:
                    self.logger.warning(f"淡出处理异常，直接复制: {e}")
                    import shutil
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                    # 降级处理：直接复制
                    import shutil
                    shutil.copy2(audio_path, output_path)
                    return True
            
            # 如果实际时长 > 目标时长，进行时间压缩
            # 让倍速比计算得到的倍速大一点，确保不超出分段时间戳
            speed_ratio = actual_duration / target_duration  # 基础倍速
            enhanced_speed_ratio = speed_ratio * 1.10  # 增加10%确保不超出
            self.logger.info(f"音频过长 ({actual_duration:.2f}s > {target_duration:.2f}s)，基础倍速 {speed_ratio:.2f}，增强倍速 {enhanced_speed_ratio:.2f}")
            
            # 严格限制倍速不超过2.0
            if enhanced_speed_ratio > self.max_speed_ratio:
                # 倍速超过限制，使用最大允许倍速
                self.logger.warning(f"倍速过快 ({enhanced_speed_ratio:.2f} > {self.max_speed_ratio:.2f} 倍速)，限制为最大倍速 {self.max_speed_ratio:.2f}")
                final_speed_ratio = self.max_speed_ratio
            else:
                # 使用增强倍速
                final_speed_ratio = enhanced_speed_ratio
                self.logger.info(f"使用增强倍速 {enhanced_speed_ratio:.2f}，确保不超出分段时间戳")
            
            # 进行时间压缩（严格限制在2.0倍速以内）
            # 使用临时文件进行多步处理
            import tempfile
            temp_dir = tempfile.mkdtemp()
            temp_file = os.path.join(temp_dir, "temp_speed.wav")
            
            try:
                # 对于倍速超过1.2的情况，分两步处理以减少失真
                speed_processed_file = temp_file
                
                if final_speed_ratio > 1.2:
                    # 第一步：使用较低的倍速（1.2）处理
                    first_speed = 1.2
                    remaining_ratio = final_speed_ratio / first_speed
                    
                    self.logger.info(f"分步倍速处理：第一步 {first_speed:.2f}x，剩余 {remaining_ratio:.2f}x")
                    
                    # 第一步处理
                    cmd1 = [
                        'ffmpeg',
                        '-i', audio_path,
                        '-af', f'atempo={first_speed}',
                        '-y', temp_file
                    ]
                    result1 = subprocess.run(cmd1, capture_output=True, text=True)
                    
                    if result1.returncode != 0:
                        self.logger.error(f"第一步倍速处理失败: {result1.stderr}")
                        return False
                    
                    # 第二步：对剩余倍速进行处理
                    if remaining_ratio > 1.0:
                        temp_file2 = os.path.join(temp_dir, "temp_speed2.wav")
                        cmd2 = [
                            'ffmpeg',
                            '-i', temp_file,
                            '-af', f'atempo={remaining_ratio}',
                            '-y', temp_file2
                        ]
                        result2 = subprocess.run(cmd2, capture_output=True, text=True)
                        
                        if result2.returncode != 0:
                            self.logger.error(f"第二步倍速处理失败: {result2.stderr}")
                            return False
                        
                        speed_processed_file = temp_file2
                    else:
                        # 如果剩余倍速<=1，直接使用第一步结果
                        speed_processed_file = temp_file
                else:
                    # 倍速<=1.2，单次处理
                    cmd = [
                        'ffmpeg',
                        '-i', audio_path,
                        '-af', f'atempo={final_speed_ratio}',
                        '-y', temp_file
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        self.logger.error(f"倍速处理失败: {result.stderr}")
                        return False
                    
                    speed_processed_file = temp_file
                
                # 验证压缩后的时长
                compressed_duration = self.get_original_audio_duration(speed_processed_file)
                
                # 添加音频质量检查：检测末尾异常峰值
                audio_data, sr = librosa.load(speed_processed_file, sr=None)
                if len(audio_data) > 0:
                    # 检查音频末尾最后50ms的峰值
                    tail_samples = int(0.05 * sr)  # 50ms
                    tail_samples = min(tail_samples, len(audio_data))
                    if tail_samples > 0:
                        tail_audio = audio_data[-tail_samples:]
                        tail_max_amplitude = np.max(np.abs(tail_audio))
                        
                        # 如果末尾峰值超过平均峰值的3倍，可能存在问题
                        overall_max = np.max(np.abs(audio_data))
                        if overall_max > 0:
                            tail_ratio = tail_max_amplitude / overall_max
                            if tail_ratio > 0.8:
                                self.logger.warning(f"检测到音频末尾可能存在问题（峰值比: {tail_ratio:.2f}），应用低通滤波")
                                # 应用低通滤波去除高频噪声
                                import scipy.signal
                                nyquist = sr / 2
                                cutoff = min(8000, nyquist * 0.9)  # 8kHz低通滤波
                                b, a = scipy.signal.butter(4, cutoff / nyquist, btype='low')
                                audio_data = scipy.signal.filtfilt(b, a, audio_data)
                                # 保存滤波后的音频
                                sf.write(speed_processed_file, audio_data, sr)
                                self.logger.info(f"低通滤波完成: 截止频率 {cutoff:.0f}Hz")
                
                # 添加音频末尾淡出效果以减少数字伪影
                fade_out_duration = 0.02  # 20ms淡出
                fade_start_time = max(0, compressed_duration - fade_out_duration)
                
                # 使用FFmpeg添加淡出效果
                final_output = os.path.join(temp_dir, "final_with_fade.wav")
                cmd_fade = [
                    'ffmpeg',
                    '-i', speed_processed_file,
                    '-af', f'afade=t=out:st={fade_start_time:.3f}:d={fade_out_duration:.3f}',
                    '-y', final_output
                ]
                
                result_fade = subprocess.run(cmd_fade, capture_output=True, text=True)
                
                if result_fade.returncode == 0:
                    import shutil
                    shutil.copy2(final_output, output_path)
                    self.logger.info(f"音频末尾淡出处理完成: {fade_out_duration*1000:.0f}ms")
                else:
                    # 如果淡出处理失败，使用原始倍速处理结果
                    self.logger.warning(f"淡出处理失败，使用原始音频: {result_fade.stderr}")
                    import shutil
                    shutil.copy2(speed_processed_file, output_path)
                
                # 最终验证
                final_duration = self.get_original_audio_duration(output_path)
                self.logger.info(f"倍速处理：{actual_duration:.2f}s -> {target_duration:.2f}s，最终倍速 {final_speed_ratio:.2f}")
                self.logger.info(f"音频时长调整成功: {actual_duration:.2f}s -> {final_duration:.2f}s")
                
                # 清理临时文件
                import shutil
                shutil.rmtree(temp_dir)
                
                return True
                
            except Exception as e:
                self.logger.error(f"倍速处理异常: {e}")
                # 清理临时文件
                import shutil
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                return False
                
        except Exception as e:
            self.logger.error(f"调整音频时长失败: {e}")
            return False
    
    def _analyze_original_audio_ratio(self, output_dir: str, target_sample_rate: int) -> tuple:
        """
        分析原始音频中背景音乐和人声的相对比例
        
        Args:
            output_dir: 输出目录路径
            target_sample_rate: 目标采样率
            
        Returns:
            (原始人声RMS, 原始背景音乐RMS) 的元组
        """
        try:
            # 加载分离后的人声和背景音乐
            vocals_path = os.path.join(output_dir, "02_vocals.wav")
            accompaniment_path = os.path.join(output_dir, "02_accompaniment.wav")
            
            if os.path.exists(vocals_path) and os.path.exists(accompaniment_path):
                vocals, vocals_sr = librosa.load(vocals_path, sr=None)
                accompaniment, accomp_sr = librosa.load(accompaniment_path, sr=None)
                
                # 统一采样率
                if vocals_sr != target_sample_rate:
                    vocals = librosa.resample(vocals, orig_sr=vocals_sr, target_sr=target_sample_rate, res_type='kaiser_best')
                if accomp_sr != target_sample_rate:
                    accompaniment = librosa.resample(accompaniment, orig_sr=accomp_sr, target_sr=target_sample_rate, res_type='kaiser_best')
                
                # 调整长度以匹配
                min_length = min(len(vocals), len(accompaniment))
                vocals = vocals[:min_length]
                accompaniment = accompaniment[:min_length]
                
                # 计算RMS
                original_voice_rms = np.sqrt(np.mean(vocals**2))
                original_accomp_rms = np.sqrt(np.mean(accompaniment**2))
                
                if original_accomp_rms > 0:
                    original_ratio = original_voice_rms / original_accomp_rms
                    self.logger.info(f"📊 原始音频比例分析:")
                    self.logger.info(f"  原始人声RMS: {original_voice_rms:.6f}")
                    self.logger.info(f"  原始背景音乐RMS: {original_accomp_rms:.6f}")
                    self.logger.info(f"  原始人声/背景音乐比例: {original_ratio:.2f}x")
                    return (original_voice_rms, original_accomp_rms)
                else:
                    self.logger.warning("原始背景音乐RMS为0，无法计算比例")
                    return (None, None)
            else:
                self.logger.warning("未找到原始人声或背景音乐文件，无法分析原始比例")
                return (None, None)
        except Exception as e:
            self.logger.warning(f"分析原始音频比例失败: {e}")
            return (None, None)
    
    def _balance_audio_levels(self, voice_audio: np.ndarray, background_audio: np.ndarray, 
                             original_voice_rms: Optional[float] = None, 
                             original_accomp_rms: Optional[float] = None) -> np.ndarray:
        """
        平衡人声和背景音乐的音量，保持原始音频的相对比例
        
        Args:
            voice_audio: 人声音频数据
            background_audio: 背景音乐音频数据
            original_voice_rms: 原始人声RMS（可选）
            original_accomp_rms: 原始背景音乐RMS（可选）
            
        Returns:
            平衡后的音频数据
        """
        try:
            # 计算RMS音量
            voice_rms = np.sqrt(np.mean(voice_audio**2))
            background_rms = np.sqrt(np.mean(background_audio**2))
            
            self.logger.info(f"🔊 音量分析:")
            self.logger.info(f"  克隆人声RMS: {voice_rms:.4f}")
            self.logger.info(f"  背景音乐RMS: {background_rms:.4f}")
            
            # 如果提供了原始比例，使用原始比例；否则使用固定目标比例
            if original_voice_rms is not None and original_accomp_rms is not None and original_accomp_rms > 0:
                # 保持原始音频中背景音乐和人声的相对比例
                original_ratio = original_voice_rms / original_accomp_rms
                self.logger.info(f"  使用原始比例: 人声/背景音乐 = {original_ratio:.2f}x")
                
                # 修复：基于原始人声RMS设置目标，而不是固定0.3-0.5
                # 如果克隆人声RMS >= 原始人声RMS，使用原始人声RMS作为目标
                # 如果克隆人声RMS < 原始人声RMS，适度放大但不超过原始人声RMS的1.2倍
                if voice_rms > 0:
                    if voice_rms >= original_voice_rms:
                        # 克隆人声已经足够大，使用原始人声RMS作为目标（保持或略微降低）
                        target_voice_rms = original_voice_rms
                        self.logger.info(f"  克隆人声RMS ({voice_rms:.4f}) >= 原始人声RMS ({original_voice_rms:.4f})，使用原始人声RMS作为目标")
                    else:
                        # 克隆人声较小，适度放大但不超过原始人声RMS的1.2倍
                        target_voice_rms = min(original_voice_rms * 1.2, max(voice_rms, original_voice_rms * 0.9))
                        self.logger.info(f"  克隆人声RMS ({voice_rms:.4f}) < 原始人声RMS ({original_voice_rms:.4f})，适度放大到 {target_voice_rms:.4f}")
                    
                    voice_gain = target_voice_rms / voice_rms
                    voice_gain = np.clip(voice_gain, 0.1, 3.0)  # 限制人声增益
                else:
                    voice_gain = 1.0
                    target_voice_rms = original_voice_rms if original_voice_rms else 0.3
                
                # 根据原始比例，计算背景音乐的目标RMS
                target_background_rms = target_voice_rms / original_ratio
                
                # 计算背景音乐增益
                if background_rms > 0:
                    background_gain = target_background_rms / background_rms
                    # 限制背景音乐增益，避免过度放大（最大1.2x，更保守）
                    # 如果计算出的增益小于1.0，说明背景音乐已经足够大，不需要放大
                    background_gain = np.clip(background_gain, 0.0, 1.2)
                    
                    # 额外检查：如果目标背景音乐RMS比原始背景音乐RMS大很多，进一步限制
                    if target_background_rms > original_accomp_rms * 1.5:
                        self.logger.warning(f"  ⚠️ 目标背景音乐RMS ({target_background_rms:.4f}) 比原始背景音乐RMS ({original_accomp_rms:.4f}) 大很多，限制增益")
                        # 限制目标背景音乐RMS不超过原始背景音乐RMS的1.2倍
                        target_background_rms = original_accomp_rms * 1.2
                        background_gain = target_background_rms / background_rms
                        background_gain = np.clip(background_gain, 0.0, 1.2)
                    
                    # 关键修复：如果人声被降低（增益<1.0），背景音乐也应该相应降低，以保持相对比例
                    if voice_gain < 1.0 and background_gain > voice_gain:
                        self.logger.info(f"  🔧 人声被降低（增益 {voice_gain:.2f}x），限制背景音乐增益不超过人声增益，以保持相对比例")
                        background_gain = min(background_gain, voice_gain)
                        # 重新计算目标背景音乐RMS（基于限制后的增益）
                        target_background_rms = background_rms * background_gain
                else:
                    background_gain = 0.0
                
                self.logger.info(f"  目标人声RMS: {target_voice_rms:.4f} (原始: {original_voice_rms:.4f})")
                self.logger.info(f"  目标背景音乐RMS: {target_background_rms:.4f} (原始: {original_accomp_rms:.4f}, 保持原始比例 {original_ratio:.2f}x)")
            else:
                # 回退到固定目标比例（如果无法获取原始比例）
                self.logger.info(f"  使用固定目标比例（无法获取原始比例）")
                if voice_rms > 0.1:
                    voice_target_ratio = 0.5  # 人声占50%
                else:
                    voice_target_ratio = 0.6  # 人声占60%
                background_target_ratio = 0.2  # 背景音乐占20%（降低，减少干扰）
                
                # 计算调整系数
                if voice_rms > 0:
                    voice_gain = voice_target_ratio / voice_rms
                else:
                    voice_gain = 1.0
                    
                if background_rms > 0:
                    background_gain = background_target_ratio / background_rms
                else:
                    background_gain = 0.0
                
                # 限制增益范围
                voice_gain = np.clip(voice_gain, 0.1, 3.0)
                background_gain = np.clip(background_gain, 0.0, 1.5)  # 降低背景音乐最大增益
            
            self.logger.info(f"  人声增益: {voice_gain:.2f}x")
            self.logger.info(f"  背景音乐增益: {background_gain:.2f}x")
            
            # 应用增益
            balanced_voice = voice_audio * voice_gain
            balanced_background = background_audio * background_gain
            
            # 防止削波：在混合前检查峰值
            voice_peak = np.max(np.abs(balanced_voice))
            background_peak = np.max(np.abs(balanced_background))
            estimated_peak = voice_peak + background_peak
            
            if estimated_peak > 1.0:
                self.logger.warning(f"  ⚠️ 检测到可能削波（估计峰值: {estimated_peak:.4f} > 1.0），先归一化")
                # 如果估计峰值超过1.0，先归一化两个音频
                if voice_peak > 0:
                    balanced_voice = balanced_voice / max(voice_peak, 0.7)  # 归一化到0.7，留出空间给背景音乐
                if background_peak > 0:
                    balanced_background = balanced_background / max(background_peak, 0.3)  # 归一化到0.3
            
            # 合并音频
            final_audio = balanced_voice + balanced_background
            
            # 检查混合后的峰值，防止削波
            final_peak = np.max(np.abs(final_audio))
            if final_peak > 1.0:
                self.logger.warning(f"  ⚠️ 混合后检测到削波（峰值: {final_peak:.4f} > 1.0），进行归一化")
                final_audio = final_audio / final_peak * 0.99  # 归一化到0.99，避免完全削波
            
            # 计算最终音量
            final_rms = np.sqrt(np.mean(final_audio**2))
            final_peak_after = np.max(np.abs(final_audio))
            self.logger.info(f"  最终音频RMS: {final_rms:.4f}")
            self.logger.info(f"  最终峰值: {final_peak_after:.4f}")
            
            return final_audio
            
        except Exception as e:
            self.logger.error(f"音频音量平衡失败: {e}")
            # 如果平衡失败，使用简单相加
            return voice_audio + background_audio * 0.3
    
    def _normalize_audio_volume(self, audio: np.ndarray) -> np.ndarray:
        """
        保持与原视频相近的音量，只做轻微的峰值标准化
        
        Args:
            audio: 输入音频数据
            
        Returns:
            标准化后的音频数据
        """
        try:
            # 计算当前峰值
            current_peak = np.max(np.abs(audio))
            
            if current_peak == 0:
                self.logger.warning("音频数据为空，跳过音量标准化")
                return audio
            
            # 防止削波：如果峰值已经超过1.0，先归一化
            if current_peak > 1.0:
                self.logger.warning(f"  ⚠️ 检测到削波（峰值: {current_peak:.4f} > 1.0），先归一化")
                audio = audio / current_peak * 0.99  # 归一化到0.99
                current_peak = 0.99
            
            # 目标峰值：与原视频完全一致或稍微小一点点
            # 如果原始峰值已经很高，稍微降低5%；如果较低，适当提升
            if current_peak > 0.95:
                target_peak = current_peak * 0.95  # 稍微降低5%
            elif current_peak > 0.8:
                target_peak = 0.9  # 适当提升到90%
            else:
                target_peak = 0.9  # 提升到90%
            
            # 计算增益
            gain = target_peak / current_peak
            
            # 限制增益范围，避免过度放大或缩小
            # 如果音频已经很响，稍微降低；如果较低，适度提升
            if current_peak > 0.95:
                gain = 0.95  # 稍微降低5%
            elif current_peak > 0.8:
                gain = min(gain, 1.2)  # 最多放大20%
            else:
                gain = min(gain, 1.5)  # 最多放大50%（降低从2.0到1.5）
            
            # 应用增益
            normalized_audio = audio * gain
            
            # 再次检查峰值，确保不超过1.0
            final_peak = np.max(np.abs(normalized_audio))
            if final_peak > 1.0:
                self.logger.warning(f"  ⚠️ 增益后检测到削波（峰值: {final_peak:.4f} > 1.0），进行最终归一化")
                normalized_audio = normalized_audio / final_peak * 0.99
                final_peak = 0.99
            
            # 计算最终音量信息
            final_rms = np.sqrt(np.mean(normalized_audio**2))
            
            self.logger.info(f"🔊 音量调整:")
            self.logger.info(f"  原始峰值: {current_peak:.4f}")
            self.logger.info(f"  目标峰值: {target_peak:.4f}")
            self.logger.info(f"  应用增益: {gain:.2f}x")
            self.logger.info(f"  最终RMS: {final_rms:.4f}")
            self.logger.info(f"  最终峰值: {final_peak:.4f}")
            
            return normalized_audio
            
        except Exception as e:
            self.logger.error(f"音量调整失败: {e}")
            # 如果调整失败，保持原音量
            return audio
