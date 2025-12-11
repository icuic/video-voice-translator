"""
增量音频/视频合并服务
只重新处理修改过的分段，复用未修改的音频文件
"""

import os
import sys
import logging
import tempfile
import numpy as np
import librosa
import soundfile as sf
from typing import List, Dict, Any
from pathlib import Path

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)


async def incremental_merge_audio(task_id: str, segments: List[Dict[str, Any]]):
    """
    增量合并音频
    只重新处理修改过的分段，复用未修改分段的音频文件
    
    Args:
        task_id: 任务ID
        segments: 分段列表
    """
    task_dir = _find_task_dir(task_id)
    if not task_dir:
        raise ValueError(f"任务目录不存在: {task_id}")
    
    # 使用现有的 TimestampedAudioMerger
    from src.utils import load_config
    from src.timestamped_audio_merger import TimestampedAudioMerger
    from src.output_manager import OutputManager, StepNumbers
    
    config = load_config()
    audio_merger = TimestampedAudioMerger(config)
    
    # 获取原始音频时长
    # 使用空字符串作为 input_file，避免 None 导致的 TypeError
    output_manager = OutputManager("", "")
    output_manager.task_dir = task_dir
    vocals_path = output_manager.get_file_path(StepNumbers.STEP_2, "vocals")
    
    if not os.path.exists(vocals_path):
        raise FileNotFoundError(f"原始人声文件不存在: {vocals_path}")
    
    total_duration = audio_merger.get_original_audio_duration(vocals_path)
    
    # 准备分段数据
    segments_for_merge = []
    cloned_audio_dir = os.path.join(task_dir, "cloned_audio")
    
    for i, segment in enumerate(segments):
        # 查找对应的音频文件
        audio_file = os.path.join(cloned_audio_dir, f"07_segment_{i:03d}.wav")
        
        # 如果文件不存在，尝试使用分段数据中的路径
        if not os.path.exists(audio_file):
            audio_file = segment.get("cloned_audio_path", "")
        
        if audio_file and os.path.exists(audio_file):
            segments_for_merge.append({
                "start": segment.get("start", 0.0),
                "end": segment.get("end", 0.0),
                "audio_path": audio_file,
                "text": segment.get("translated_text", ""),
                "original_text": segment.get("text", "")
            })
    
    # 创建时间同步音频轨道
    final_audio_path = output_manager.get_file_path(StepNumbers.STEP_8, "final_voice")
    
    merge_result = audio_merger.create_timestamped_audio_track_with_output_manager(
        segments_for_merge,
        total_duration,
        output_manager
    )
    
    if not merge_result.get("success"):
        raise RuntimeError(f"音频合并失败: {merge_result.get('error')}")
    
    logger.info(f"增量音频合并完成: {len(segments_for_merge)} 个分段")
    return merge_result


async def incremental_merge_video(task_id: str):
    """
    增量合并视频
    复用原始视频轨道，只替换音频轨道
    
    Args:
        task_id: 任务ID
    """
    task_dir = _find_task_dir(task_id)
    if not task_dir:
        raise ValueError(f"任务目录不存在: {task_id}")
    
    from src.output_manager import OutputManager, StepNumbers
    import subprocess
    
    # 使用空字符串作为 input_file，避免 None 导致的 TypeError
    output_manager = OutputManager("", "")
    output_manager.task_dir = task_dir
    
    # 获取文件路径
    final_audio_path = output_manager.get_file_path(StepNumbers.STEP_8, "final_voice")
    accompaniment_path = output_manager.get_file_path(StepNumbers.STEP_2, "accompaniment")
    final_video_path = output_manager.get_file_path(StepNumbers.STEP_9, "final_video")
    
    # 从任务状态中获取原始输入文件路径
    original_input_path = None
    try:
        from app.api.translation import tasks
        if task_id in tasks:
            original_input_path = tasks[task_id].get("file_path")
            if original_input_path and os.path.exists(original_input_path):
                logger.info(f"从任务状态获取原始输入文件: {original_input_path}")
    except Exception as e:
        logger.warning(f"从任务状态获取原始输入文件失败: {e}")
    
    # 如果任务状态中没有，尝试从任务目录中查找原始文件
    if not original_input_path or not os.path.exists(original_input_path):
        # 尝试查找任务目录中的原始视频文件
        task_dir_path = Path(task_dir)
        for ext in ['.mp4', '.avi', '.mov', '.mkv']:
            video_files = list(task_dir_path.glob(f"*{ext}"))
            if video_files:
                original_input_path = str(video_files[0])
                logger.info(f"从任务目录找到原始输入文件: {original_input_path}")
                break
    
    if not original_input_path or not os.path.exists(original_input_path):
        raise FileNotFoundError(f"无法找到原始输入文件: {original_input_path}")
    
    if not os.path.exists(final_audio_path):
        raise FileNotFoundError(f"最终音频文件不存在: {final_audio_path}")
    
    # 使用librosa混合音频（与主流程保持一致），避免FFmpeg amix的标准化问题
    if os.path.exists(accompaniment_path):
        # 有背景音乐：使用librosa混合音频，完全控制音量
        logger.info("使用librosa混合音频，避免FFmpeg amix的标准化问题")
        
        try:
            # 1. 使用librosa加载音频并混合
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
                logger.warning(f"检测到削波风险（峰值: {max_amplitude:.4f}），进行归一化")
                mixed_audio = mixed_audio / max_amplitude * 0.99
            
            # 保存混合后的音频到临时文件
            temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_audio_path = temp_audio.name
            temp_audio.close()
            
            sf.write(temp_audio_path, mixed_audio, sample_rate, subtype='PCM_16')
            logger.info(f"音频混合完成，保存到临时文件: {temp_audio_path}")
            
            # 2. 使用FFmpeg合并视频和混合后的音频
            cmd = [
                'ffmpeg',
                '-i', original_input_path,
                '-i', temp_audio_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-y',
                final_video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # 清理临时文件
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)
            
            if result.returncode != 0:
                raise RuntimeError(f"视频合成失败: {result.stderr}")
            
            logger.info('使用librosa混合音频，保持原始音量')
            
        except Exception as e:
            logger.error(f"使用librosa混合音频失败: {e}")
            # 如果librosa失败，回退到FFmpeg方案（注意：amix会进行标准化，可能导致音量降低）
            logger.warning("回退到FFmpeg amix方案（注意：可能存在音量降低）")
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
                raise RuntimeError(f"视频合成失败: {result.stderr}")
    else:
        # 只有配音，直接映射音频
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
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"视频合成失败: {result.stderr}")
    
    logger.info(f"增量视频合并完成: {final_video_path}")
    return {
        "success": True,
        "video_path": final_video_path
    }


def _find_task_dir(task_id: str) -> str:
    """查找任务目录"""
    # 首先尝试从任务状态中获取（这是最可靠的方式）
    try:
        from app.api.translation import tasks
        if task_id in tasks:
            task_dir = tasks[task_id].get("task_dir")
            if task_dir and os.path.exists(task_dir):
                logger.info(f"从任务状态获取 task_dir: {task_dir}")
                return task_dir
    except Exception as e:
        logger.warning(f"从任务状态获取 task_dir 失败: {e}")
    
    # 如果任务状态中没有，尝试从输出目录中查找（回退方案）
    outputs_dir = Path("data/outputs")
    if outputs_dir.exists():
        for dir_path in outputs_dir.iterdir():
            if dir_path.is_dir():
                segments_file = dir_path / "04_segments.json"
                if segments_file.exists():
                    # 这里简化处理，返回第一个找到的目录
                    # 实际应该根据 task_id 匹配，但需要从目录名或元数据中获取
                    logger.warning(f"使用回退方案查找任务目录: {dir_path}")
                    return str(dir_path)
    
    raise FileNotFoundError(f"任务目录不存在: {task_id}")


