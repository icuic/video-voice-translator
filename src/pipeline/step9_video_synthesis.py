"""
步骤9: 视频合成
视频合成
"""

import os
import subprocess
import shutil
import tempfile
import numpy as np
import librosa
import soundfile as sf
from typing import Dict, Any, Optional
from ..output_manager import OutputManager, StepNumbers
from .base_step import BaseStep
from .processing_context import ProcessingContext


class Step9VideoSynthesis(BaseStep):
    """步骤9: 视频合成"""
    
    def _analyze_audio_volume(self, audio_path: str) -> Optional[float]:
        """
        分析音频文件的平均音量（dB）
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            平均音量值（dB），如果分析失败返回None
        """
        try:
            cmd = [
                'ffmpeg',
                '-i', audio_path,
                '-af', 'volumedetect',
                '-f', 'null',
                '-'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # 解析FFmpeg输出中的音量信息
            for line in result.stderr.split('\n'):
                if 'mean_volume:' in line:
                    # 提取音量值，格式如：mean_volume: -20.5 dB
                    parts = line.split('mean_volume:')
                    if len(parts) > 1:
                        volume_str = parts[1].strip().split()[0]
                        return float(volume_str)
            
            self.logger.warning(f"无法解析音频音量: {audio_path}")
            return None
        except Exception as e:
            self.logger.error(f"分析音频音量失败: {e}")
            return None
    
    def execute(self) -> Dict[str, Any]:
        """执行步骤9: 视频合成"""
        
        # 读取最终音频文件
        final_audio_path = self.output_manager.get_file_path(StepNumbers.STEP_8, "final_voice")
        if not os.path.exists(final_audio_path):
            return {
                "success": False,
                "error": f"最终音频文件不存在: {final_audio_path}"
            }
        
        # 读取元数据
        metadata = self.context.load_metadata()
        
        # 读取原始输入文件
        original_file = os.path.join(self.task_dir, "00_original_input.*")
        # 查找原始文件（可能扩展名不同）
        original_input_path = None
        for ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg']:
            test_path = os.path.join(self.task_dir, f"00_original_input{ext}")
            if os.path.exists(test_path):
                original_input_path = test_path
                break
        
        if not original_input_path:
            return {
                "success": False,
                "error": "原始输入文件不存在"
            }
        
        # 使用OutputManager生成最终输出路径
        final_video_path = self.output_manager.get_file_path(StepNumbers.STEP_9, "final_video")
        
        if self.context.is_video:
            # 视频文件：合并原始视频、中文配音和背景音乐
            self.logger.info("合并视频、中文配音和背景音乐...")
            
            # 检查是否存在背景音乐文件
            accompaniment_path = self.output_manager.get_file_path(StepNumbers.STEP_2, "accompaniment")
            if os.path.exists(accompaniment_path):
                # 三个输入：原始视频、中文配音、背景音乐
                # 从源头消除音量差异：使用librosa混合音频，完全控制音量，避免FFmpeg amix的标准化问题
                
                self.logger.info("使用librosa混合音频，避免FFmpeg amix的标准化问题")
                
                # 1. 使用librosa加载音频并混合
                try:
                    # 加载音频文件
                    voice_audio, voice_sr = librosa.load(final_audio_path, sr=None)
                    accompaniment_audio, accomp_sr = librosa.load(accompaniment_path, sr=None)
                    
                    # 统一采样率
                    if voice_sr != accomp_sr:
                        if voice_sr > accomp_sr:
                            accompaniment_audio = librosa.resample(accompaniment_audio, orig_sr=accomp_sr, target_sr=voice_sr, res_type='kaiser_best')
                            sample_rate = voice_sr
                        else:
                            voice_audio = librosa.resample(voice_audio, orig_sr=voice_sr, target_sr=accomp_sr, res_type='kaiser_best')
                            sample_rate = accomp_sr
                    else:
                        sample_rate = voice_sr
                    
                    # 调整长度以匹配（以较长的为准）
                    max_length = max(len(voice_audio), len(accompaniment_audio))
                    if len(voice_audio) < max_length:
                        voice_audio = np.pad(voice_audio, (0, max_length - len(voice_audio)), mode='constant')
                    if len(accompaniment_audio) < max_length:
                        accompaniment_audio = np.pad(accompaniment_audio, (0, max_length - len(accompaniment_audio)), mode='constant')
                    
                    # 降低背景音乐音量到30%
                    accompaniment_audio = accompaniment_audio * 0.3
                    
                    # 混合音频（直接相加，保持原始音量）
                    mixed_audio = voice_audio + accompaniment_audio
                    
                    # 防止削波：如果峰值超过0.99，进行归一化
                    max_amplitude = np.max(np.abs(mixed_audio))
                    if max_amplitude > 0.99:
                        self.logger.warning(f"检测到削波风险（峰值: {max_amplitude:.4f}），进行归一化")
                        mixed_audio = mixed_audio / max_amplitude * 0.99
                    
                    # 保存混合后的音频到临时文件
                    temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                    temp_audio_path = temp_audio.name
                    temp_audio.close()
                    
                    sf.write(temp_audio_path, mixed_audio, sample_rate, subtype='PCM_16')
                    self.logger.info(f"音频混合完成，保存到临时文件: {temp_audio_path}")
                    
                    # 2. 使用FFmpeg合并视频和混合后的音频
                    cmd = [
                        'ffmpeg',
                        '-i', original_input_path,        # 原始视频
                        '-i', temp_audio_path,             # 混合后的音频
                        '-c:v', 'copy',
                        '-c:a', 'aac',
                        '-map', '0:v:0',                  # 使用原始视频
                        '-map', '1:a:0',                  # 使用混合后的音频
                        '-y',
                        final_video_path
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    # 清理临时文件
                    if os.path.exists(temp_audio_path):
                        os.unlink(temp_audio_path)
                    
                    if result.returncode != 0:
                        return {
                            "success": False,
                            "error": f"视频创建失败: {result.stderr}"
                        }
                    
                    self.logger.info(f'使用背景音乐（已降低到30%音量）: {accompaniment_path}')
                    self.logger.info('使用librosa混合音频，保持原始音量')
                    
                except Exception as e:
                    self.logger.error(f"使用librosa混合音频失败: {e}")
                    # 如果librosa失败，回退到FFmpeg方案（注意：amix会进行标准化，可能导致音量降低）
                    self.logger.warning("回退到FFmpeg amix方案（注意：可能存在音量降低）")
                    cmd = [
                        'ffmpeg',
                        '-i', original_input_path,
                        '-i', final_audio_path,
                        '-i', accompaniment_path,
                        '-c:v', 'copy',
                        '-c:a', 'aac',
                        '-filter_complex', '[2:a]volume=0.3[accompaniment_low];[1:a][accompaniment_low]amix=inputs=2:duration=first:weights="2 1"[aout]',
                        '-map', '0:v:0',
                        '-map', '[aout]',
                        '-y',
                        final_video_path
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        return {
                            "success": False,
                            "error": f"视频创建失败: {result.stderr}"
                        }
            else:
                # 没有背景音乐，直接映射音频
                # 只有两个输入：原始视频、中文配音
                # 直接映射音频，保持原音量
                cmd = [
                    'ffmpeg',
                    '-i', original_input_path,
                    '-i', final_audio_path,
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                    '-y',
                    final_video_path
                ]
                self.logger.warning('未找到背景音乐文件，仅使用中文配音')
                result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"视频创建失败: {result.stderr}"
                }
            
            self.logger.info(f'最终翻译视频创建成功: {final_video_path}')
            self.output_manager.log(f"步骤9完成: 最终翻译视频创建成功: {final_video_path}")
            
        else:
            # 音频文件：只输出中文配音音频
            self.logger.info("输出中文配音音频...")
            # 替换扩展名为 .wav（步骤8输出的就是.wav格式），保持新命名格式（如果已应用）
            base_name = os.path.splitext(final_video_path)[0]
            final_video_path = f"{base_name}.wav"
            shutil.copy2(final_audio_path, final_video_path)
            
            self.logger.info(f'中文配音音频已保存: {final_video_path}')
            self.output_manager.log(f"步骤9完成: 中文配音音频已保存: {final_video_path}")
        
        return {
            "success": True,
            "final_video_path": final_video_path,
            "is_video": self.context.is_video
        }

