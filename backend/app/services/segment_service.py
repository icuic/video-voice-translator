"""
分段服务
调用 ./src/ 中的现有业务逻辑实现分段操作
"""

import os
import sys
import json
import logging
import shutil
import tempfile
from typing import List, Dict, Any, Optional
from pathlib import Path
import wave
import audioop

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)


def _cut_audio_segment(audio_path: str, start_time: float, end_time: float,
                      task_id: str, segment_id: int) -> Optional[str]:
    """
    切分音频片段

    Args:
        audio_path: 原始音频文件路径
        start_time: 开始时间（秒）
        end_time: 结束时间（秒）
        task_id: 任务ID
        segment_id: 分段ID

    Returns:
        切分后的音频文件路径，如果失败返回None
    """
    try:
        import ffmpeg

        # 查找任务目录
        task_dir = _find_task_dir(task_id)
        if not task_dir:
            return None

        # 创建ref_audio目录
        ref_audio_dir = os.path.join(task_dir, "ref_audio")
        os.makedirs(ref_audio_dir, exist_ok=True)

        # 输出文件路径
        output_path = os.path.join(ref_audio_dir, f"06_ref_segment_{segment_id:03d}.wav")

        # 使用ffmpeg切分音频
        duration = end_time - start_time
        if duration <= 0:
            logger.warning(f"无效的音频时长: {duration}")
            return None

        # 切分音频
        try:
            # 对于从0秒开始的音频，稍微偏移一点避免FFmpeg问题
            actual_start = max(start_time, 0.001) if start_time == 0 else start_time
            actual_duration = duration - (actual_start - start_time) if start_time == 0 else duration

            stream = ffmpeg.input(audio_path, ss=actual_start, t=actual_duration)
            stream = ffmpeg.output(stream, output_path, acodec='pcm_s16le', ac=1, ar=16000)
            ffmpeg.run(stream, quiet=True, overwrite_output=True)
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg切分失败: {e}")
            # 如果FFmpeg失败，尝试直接复制文件（仅适用于从0秒开始的情况）
            if start_time == 0:
                try:
                    import shutil
                    shutil.copy2(audio_path, output_path)
                    logger.info(f"FFmpeg失败，使用文件复制: {output_path}")
                    return output_path
                except Exception as copy_error:
                    logger.error(f"文件复制也失败: {copy_error}")
            raise

        if os.path.exists(output_path):
            logger.info(f"音频切分成功: {output_path} ({start_time:.2f}s - {end_time:.2f}s)")
            return output_path
        else:
            logger.error(f"音频切分失败: 输出文件不存在 {output_path}")
            return None

    except Exception as e:
        logger.error(f"音频切分失败: {e}")
        return None


def safe_write_json(file_path: str, data: Any, create_backup: bool = True, 
                   max_backup_size: int = 10 * 1024 * 1024) -> None:
    """
    安全写入JSON文件（支持大文件）
    
    Args:
        file_path: 目标文件路径
        data: 要写入的数据
        create_backup: 是否创建备份
        max_backup_size: 最大备份文件大小（10MB），超过此大小不备份
    """
    # 1. 检查文件大小，决定是否备份
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    should_backup = create_backup and file_size < max_backup_size
    
    if should_backup:
        backup_file = file_path + '.backup'
        try:
            shutil.copy2(file_path, backup_file)
            logger.info(f"已创建备份: {backup_file} ({file_size / 1024:.1f}KB)")
        except Exception as e:
            logger.warning(f"创建备份失败: {e}，继续写入")
    
    # 2. 写入临时文件（使用系统临时目录，避免跨文件系统问题）
    temp_dir = os.path.dirname(file_path) or os.getcwd()
    temp_fd, temp_file = tempfile.mkstemp(
        suffix='.tmp',
        dir=temp_dir,
        prefix=os.path.basename(file_path) + '.'
    )
    
    try:
        # 写入临时文件
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            # 确保数据写入磁盘
            f.flush()
            os.fsync(f.fileno())
        
        # 3. 原子替换（在支持的操作系统上）
        shutil.move(temp_file, file_path)
        logger.info(f"文件已安全更新: {file_path} ({os.path.getsize(file_path) / 1024:.1f}KB)")
        
        # 4. 成功后删除旧备份（可选，保留最近一次备份）
        # if should_backup and os.path.exists(backup_file):
        #     os.remove(backup_file)
        
    except Exception as e:
        # 如果失败，清理临时文件
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        
        # 如果有备份，可以尝试恢复（可选）
        if should_backup and os.path.exists(backup_file):
            logger.warning(f"写入失败，可以从备份恢复: {backup_file}")
        
        raise


def get_audio_duration(file_path: str) -> Optional[float]:
    """获取音频文件时长（秒）"""
    if not file_path or not os.path.exists(file_path):
        return None

    try:
        with wave.open(file_path, 'rb') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            duration = frames / float(rate)
            return duration
    except Exception as e:
        logger.warning(f"获取音频时长失败 {file_path}: {e}")
        return None


async def _rename_audio_files_after_split(task_id: str, new_segments: List[Dict[str, Any]], split_segment_id: int):
    """
    拆分后重新命名受影响的音频文件

    Args:
        task_id: 任务ID
        new_segments: 新的分段列表（已重新编号）
        split_segment_id: 被拆分的分段ID
    """
    try:
        task_dir = _find_task_dir(task_id)
        if not task_dir:
            return

        ref_audio_dir = os.path.join(task_dir, "ref_audio")
        cloned_audio_dir = os.path.join(task_dir, "cloned_audio")

        # 重新命名ref_audio文件
        if os.path.exists(ref_audio_dir):
            await _rename_files_in_dir(ref_audio_dir, new_segments, split_segment_id)

        # 重新命名cloned_audio文件
        if os.path.exists(cloned_audio_dir):
            await _rename_files_in_dir(cloned_audio_dir, new_segments, split_segment_id)

        logger.info(f"音频文件重新命名完成: task_id={task_id}")

    except Exception as e:
        logger.error(f"音频文件重新命名失败: {e}")


async def _rename_files_in_dir(audio_dir: str, segments: List[Dict[str, Any]], split_segment_id: int):
    """
    重新命名受影响的音频文件

    由于我们只重新编号拆分点之后的分段，所以只需要重命名这些分段的音频文件。

    Args:
        audio_dir: 音频目录路径
        segments: 分段列表
        split_segment_id: 被拆分的分段ID
    """
    import glob

    # 只处理拆分点之后的分段（ID >= split_segment_id + 2）
    for segment in segments:
        segment_id = segment['id']
        if segment_id < split_segment_id + 2:
            continue  # 不需要重命名拆分前的分段

        expected_ref_filename = f"06_ref_segment_{segment_id:03d}.wav"
        expected_cloned_filename = f"07_segment_{segment_id:03d}.wav"

        # 检查ref_audio文件
        ref_audio_path = segment.get('audio_path') or segment.get('reference_audio_path')
        if ref_audio_path and os.path.dirname(ref_audio_path) == audio_dir:
            current_filename = os.path.basename(ref_audio_path)
            if current_filename != expected_ref_filename:
                # 计算原始ID（重新编号前的ID）
                original_id = segment_id - 1  # 因为插入了一个新分段
                original_filename = f"06_ref_segment_{original_id:03d}.wav"
                old_path = os.path.join(audio_dir, original_filename)

                if os.path.exists(old_path):
                    new_path = os.path.join(audio_dir, expected_ref_filename)
                    try:
                        os.rename(old_path, new_path)
                        # 更新分段中的路径
                        if segment.get('audio_path') == old_path:
                            segment['audio_path'] = new_path
                        if segment.get('reference_audio_path') == old_path:
                            segment['reference_audio_path'] = new_path
                        logger.info(f"重命名ref音频文件: {original_filename} -> {expected_ref_filename}")
                    except Exception as e:
                        logger.error(f"重命名ref音频文件失败 {original_filename}: {e}")

        # 检查cloned_audio文件
        cloned_audio_path = segment.get('cloned_audio_path')
        if cloned_audio_path and os.path.dirname(cloned_audio_path) == audio_dir:
            current_filename = os.path.basename(cloned_audio_path)
            if current_filename != expected_cloned_filename:
                # 计算原始ID
                original_id = segment_id - 1
                original_filename = f"07_segment_{original_id:03d}.wav"
                old_path = os.path.join(audio_dir, original_filename)

                if os.path.exists(old_path):
                    new_path = os.path.join(audio_dir, expected_cloned_filename)
                    try:
                        os.rename(old_path, new_path)
                        # 更新分段中的路径
                        segment['cloned_audio_path'] = new_path
                        logger.info(f"重命名cloned音频文件: {original_filename} -> {expected_cloned_filename}")
                    except Exception as e:
                        logger.error(f"重命名cloned音频文件失败 {original_filename}: {e}")


async def get_segments(task_id: str) -> List[Dict[str, Any]]:
    """获取分段列表"""
    # 查找任务目录
    task_dir = _find_task_dir(task_id)
    if not task_dir:
        raise ValueError(f"任务目录不存在: {task_id}")
    
    # 文件优先级：05_translated_segments.json > 06_segments_with_audio.json > 04_segments.json
    # 05_translated_segments.json 包含用户最新修改的翻译文本，应该是最优先的
    translated_segments_file = os.path.join(task_dir, "05_translated_segments.json")
    segments_with_audio_file = os.path.join(task_dir, "06_segments_with_audio.json")
    segments_file = os.path.join(task_dir, "04_segments.json")

    if os.path.exists(translated_segments_file):
        # 检查 05_translated_segments.json 的分段数量是否合理
        with open(translated_segments_file, 'r', encoding='utf-8') as f:
            translated_segments = json.load(f)

        if os.path.exists(segments_file):
            with open(segments_file, 'r', encoding='utf-8') as f:
                original_segments = json.load(f)

            # 如果翻译分段数量少于原始分段的一半，认为数据可能损坏，回退到原始分段
            if len(translated_segments) < len(original_segments) * 0.5:
                logger.warning(
                    f"检测到 {translated_segments_file} 的分段数量({len(translated_segments)}) "
                    f"明显少于原始分段({len(original_segments)})，可能被错误覆盖。"
                    f"回退到使用 {segments_file}"
                )
                target_file = segments_file
            else:
                target_file = translated_segments_file
                logger.info(f"使用带译文的分段文件: {translated_segments_file}")
        else:
            target_file = translated_segments_file
            logger.info(f"使用带译文的分段文件: {translated_segments_file}")
    elif os.path.exists(segments_with_audio_file):
        target_file = segments_with_audio_file
        logger.info(f"使用带音频的分段文件: {segments_with_audio_file}")
    else:
        target_file = segments_file
        if not os.path.exists(target_file):
            raise FileNotFoundError(f"分段文件不存在: {target_file}")
        logger.info(f"使用原始分段文件: {segments_file}")
    
    with open(target_file, 'r', encoding='utf-8') as f:
        segments = json.load(f)

    # 确保每个分段都有 id 字段，便于前端和后续操作使用
    if isinstance(segments, list):
        for idx, seg in enumerate(segments):
            if isinstance(seg, dict):
                # 确保有id字段
                if "id" not in seg:
                    seg["id"] = idx

                # 计算时长信息（对所有分段都执行）
                # 原始音频时长 = end - start
                original_duration = seg.get("end", 0) - seg.get("start", 0)
                seg["original_duration"] = original_duration

                # 克隆音频时长
                cloned_audio_path = seg.get("cloned_audio_path")
                if cloned_audio_path and os.path.exists(cloned_audio_path):
                    cloned_duration = get_audio_duration(cloned_audio_path)
                    if cloned_duration:
                        seg["cloned_duration"] = cloned_duration
                        # 计算速度倍率（需要多少倍速才能匹配原始时长）
                        if original_duration > 0:
                            seg["duration_multiplier"] = cloned_duration / original_duration

    return segments


async def update_segments(task_id: str, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """更新分段"""
    task_dir = _find_task_dir(task_id)
    if not task_dir:
        raise ValueError(f"任务目录不存在: {task_id}")
    
    try:
        # 验证分段数量是否合理（防止错误覆盖）
        segments_file = os.path.join(task_dir, "04_segments.json")
        if os.path.exists(segments_file):
            with open(segments_file, 'r', encoding='utf-8') as f:
                original_segments = json.load(f)
            
            # 如果传入的分段数量明显少于原始分段，可能是错误的数据
            if len(segments) < len(original_segments) * 0.5:
                logger.error(
                    f"警告：尝试保存的分段数量({len(segments)})明显少于原始分段数量({len(original_segments)})，"
                    f"这可能导致数据丢失。拒绝保存。"
                )
                raise ValueError(
                    f"分段数量异常：尝试保存 {len(segments)} 个分段，但原始有 {len(original_segments)} 个分段。"
                    f"这可能是由于数据损坏导致的。"
                )
        
        # 使用现有的保存逻辑
        from src.segment_editor import save_segments
        from src.output_manager import OutputManager
        
        # 创建 OutputManager 实例并设置 task_dir
        # 使用空字符串作为 input_file，避免 None 导致的 TypeError
        output_manager = OutputManager("", "")
        output_manager.task_dir = task_dir
        
        # 保存分段数据（不传递 all_words，避免验证过于严格）
        save_segments(segments, output_manager, all_words=None)

        # 总是更新 05_translated_segments.json，因为它应该包含用户的所有修改（包括时间戳）
        # 如果存在 06_segments_with_audio.json，从中合并音频路径信息
        segments_with_audio_file = os.path.join(task_dir, "06_segments_with_audio.json")
        if os.path.exists(segments_with_audio_file):
            try:
                with open(segments_with_audio_file, 'r', encoding='utf-8') as f:
                    audio_segments = json.load(f)

                # 合并音频路径信息
                for i, seg in enumerate(segments):
                    if i < len(audio_segments):
                        audio_seg = audio_segments[i]
                        # 保留音频相关字段
                        for key in ['audio_path', 'cloned_audio_path', 'reference_audio_path', 'original_duration', 'cloned_duration', 'duration_multiplier']:
                            if key in audio_seg:
                                seg[key] = audio_seg[key]
                logger.info(f"已从06文件合并音频路径信息")
            except Exception as e:
                logger.warning(f"合并音频路径信息失败: {e}")

        translated_segments_file = os.path.join(task_dir, "05_translated_segments.json")
        safe_write_json(translated_segments_file, segments)
        logger.info(f"已更新带译文的分段文件: {translated_segments_file}, 分段数量: {len(segments)}")

        # 如果分段包含 translated_text，同时更新 06_segments_with_audio.json，确保重新合成时使用最新的译文
        has_translated_text = any(seg.get("translated_text") for seg in segments)
        if has_translated_text:
            segments_with_audio_file = os.path.join(task_dir, "06_segments_with_audio.json")
            if os.path.exists(segments_with_audio_file):
                safe_write_json(segments_with_audio_file, segments)
                logger.info(f"已同步更新带音频的分段文件: {segments_with_audio_file}, 分段数量: {len(segments)}")
        
        logger.info(f"分段数据已保存: task_id={task_id}, segments_count={len(segments)}")
        return segments
    except Exception as e:
        logger.error(f"保存分段数据失败: task_id={task_id}, error={str(e)}", exc_info=True)
        raise


async def retranslate_segment(
    task_id: str,
    segment_id: int,
    new_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    重新翻译单个分段
    
    Args:
        task_id: 任务ID
        segment_id: 分段ID
        new_text: 可选的新翻译文本（如果提供，直接使用；否则调用LLM翻译）
    
    Returns:
        更新后的分段数据
    """
    # 获取分段列表
    segments = await get_segments(task_id)
    
    if segment_id >= len(segments):
        raise ValueError(f"分段ID超出范围: {segment_id}")
    
    segment = segments[segment_id]
    
    if new_text:
        # 用户手动输入，直接更新
        segment["translated_text"] = new_text
        logger.info(f"手动更新分段 {segment_id} 的翻译: {new_text}")
    else:
        # 自动翻译，调用现有的 TextTranslator
        from src.utils import load_config
        from src.text_translator import TextTranslator
        
        config = load_config()
        
        # 优先从任务参数文件读取语言配置（最可靠，因为文件总是存在的）
        task_dir = _find_task_dir(task_id)
        if not task_dir:
            raise ValueError(f"任务目录不存在: {task_id}")
        
        params_file = os.path.join(task_dir, "00_task_params.json")
        if os.path.exists(params_file):
            with open(params_file, 'r', encoding='utf-8') as f:
                task_params = json.load(f)
            task_source_lang = task_params.get("source_lang", "en")
            task_target_lang = task_params.get("target_lang", "zh")
            logger.info(f"从任务参数文件获取语言配置: {task_source_lang} -> {task_target_lang}")
        else:
            # 如果任务参数文件不存在，尝试从任务状态获取（备选方案）
            from app.api.translation import tasks
            if task_id in tasks:
                task_info = tasks[task_id]
                task_source_lang = task_info.get("source_language")
                task_target_lang = task_info.get("target_language")
                if task_source_lang and task_target_lang:
                    logger.info(f"从任务状态获取语言配置: {task_source_lang} -> {task_target_lang}")
                else:
                    raise ValueError(f"任务状态中缺少语言配置: source_language={task_source_lang}, target_language={task_target_lang}")
            else:
                raise ValueError(f"任务参数文件不存在且任务不在任务状态中: {params_file}")
        
        # 注意：任务参数文件中的 source_lang 已经是实际检测到的语言（如果原来是 "auto" 的话）
        # 所以这里不需要特殊处理 "auto" 的情况
        
        logger.info(f"使用任务的语言配置: {task_source_lang} -> {task_target_lang}")
        # 临时修改配置以使用任务的原始语言设置
        if "translation" not in config:
            config["translation"] = {}
        config["translation"]["source_language"] = task_source_lang
        config["translation"]["target_language"] = task_target_lang
        
        translator = TextTranslator(config)
        
        # 翻译单个分段
        result = translator.translate_segments([segment])
        if result.get("success"):
            translated_segment = result["translated_segments"][0]
            # 只更新翻译文本，保留其他字段（包括用户修改的时间戳）
            segment["translated_text"] = translated_segment.get("translated_text", "")
            segment["translation_info"] = translated_segment.get("translation_info", {})
            source_lang = config.get("translation", {}).get("source_language", "en")
            target_lang = config.get("translation", {}).get("target_language", "zh")
            logger.info(f"自动翻译分段 {segment_id} 完成 (源语言: {source_lang} -> 目标语言: {target_lang})")
        else:
            raise RuntimeError(f"翻译失败: {result.get('error')}")
    
    # 更新分段列表
    segments[segment_id] = segment
    
    # 保存更新后的分段
    await update_segments(task_id, segments)
    
    # 更新翻译文件（05_translation.txt）
    task_dir = _find_task_dir(task_id)
    if task_dir:
        _update_translation_file(task_dir, segments)
    
    return segment


async def resynthesize_segment(
    task_id: str,
    segment_id: int,
    use_original_timbre: bool = True
):
    """
    重新合成单个分段的语音
    
    Args:
        task_id: 任务ID
        segment_id: 分段ID
        use_original_timbre: 是否使用原音色
    """
    task_dir = _find_task_dir(task_id)
    if not task_dir:
        raise ValueError(f"任务目录不存在: {task_id}")
    
    # 获取分段列表
    segments = await get_segments(task_id)
    
    if segment_id >= len(segments):
        raise ValueError(f"分段ID超出范围: {segment_id}")
    
    segment = segments[segment_id]
    
    # 调用现有的 VoiceCloner
    from src.utils import load_config
    from src.voice_cloner import VoiceCloner
    from src.output_manager import OutputManager
    
    config = load_config()
    cloner = VoiceCloner(config)
    
    # 获取参考音频路径
    reference_audio_path = segment.get("reference_audio_path")
    if not reference_audio_path or not os.path.exists(reference_audio_path):
        # 尝试从任务目录中查找
        # 使用空字符串作为 input_file，避免 None 导致的 TypeError
        output_manager = OutputManager("", "")
        output_manager.task_dir = task_dir
        ref_audio_dir = os.path.join(task_dir, "ref_audio")
        if os.path.exists(ref_audio_dir):
            # 查找对应的参考音频文件
            ref_files = sorted([f for f in os.listdir(ref_audio_dir) if f.endswith('.wav')])

            # 首先尝试使用对应的 segment_id
            if segment_id < len(ref_files):
                reference_audio_path = os.path.join(ref_audio_dir, ref_files[segment_id])
            elif len(ref_files) > 0:
                # 如果没有对应文件，使用第一个可用的参考音频
                # 这种情况通常发生在分段拆分后
                reference_audio_path = os.path.join(ref_audio_dir, ref_files[0])
                logger.info(f"为分段 {segment_id} 使用默认参考音频: {reference_audio_path}")
    
    if not reference_audio_path or not os.path.exists(reference_audio_path):
        raise FileNotFoundError(f"参考音频文件不存在: segment_id={segment_id}, reference_audio_path={reference_audio_path}")
    
    # 获取翻译文本
    translated_text = segment.get("translated_text") or segment.get("text")
    if not translated_text:
        raise ValueError("分段缺少翻译文本")
    
    # 生成输出路径
    cloned_audio_dir = os.path.join(task_dir, "cloned_audio")
    os.makedirs(cloned_audio_dir, exist_ok=True)
    output_path = os.path.join(cloned_audio_dir, f"07_segment_{segment_id:03d}.wav")
    
    # 调用音色克隆
    result = cloner.clone_voice(
        reference_audio=reference_audio_path,
        text=translated_text,
        output_path=output_path,
        speaker_id=segment.get("speaker_id", f"speaker_{segment_id}")
    )
    
    if not result.get("success"):
        raise RuntimeError(f"音色克隆失败: {result.get('error')}")
    
    # 更新分段数据
    segment["cloned_audio_path"] = output_path
    segments[segment_id] = segment
    
    # 保存更新
    await update_segments(task_id, segments)
    
    # 立即通过 WebSocket 发送合成完成通知
    try:
        from app.api.websocket import send_progress
        await send_progress(task_id, {
            "type": "resynthesize_complete",
            "segment_id": segment_id,
            "audio_path": output_path,
            "success": True
        })
        logger.info(f"已发送重新合成完成通知: task_id={task_id}, segment_id={segment_id}")
    except Exception as e:
        logger.warning(f"发送WebSocket通知失败: {e}")
    
    # 注意：不再自动合并音频和视频
    # 用户需要点击"重新生成最终视频"按钮才会执行合并操作
    # 这样可以避免每次修改单个分段都重新生成整个视频，提高效率
    
    return {
        "success": True,
        "audio_path": output_path,
        "segment": segment
    }


async def merge_segments(task_id: str, segment_ids: List[int]) -> List[Dict[str, Any]]:
    """合并分段"""
    # 使用现有的合并逻辑
    from src.segment_editor import merge_segments as merge_segments_func
    
    segments = await get_segments(task_id)
    result = merge_segments_func(segments, segment_ids)
    
    # 保存更新
    await update_segments(task_id, result)
    
    return result


async def split_segment(
    task_id: str,
    segment_id: int,
    split_time: Optional[float] = None,
    split_text: Optional[str] = None,
    split_text_position: Optional[int] = None
) -> List[Dict[str, Any]]:
    """拆分分段"""
    # 使用现有的拆分逻辑
    from src.segment_editor import split_segment as split_segment_func
    
    segments = await get_segments(task_id)
    
    # 验证 segment_id
    if segment_id < 0 or segment_id >= len(segments):
        raise ValueError(f"分段ID超出范围: {segment_id}")
    
    # 获取要拆分的分段
    segment_to_split = segments[segment_id]
    
    # 调用拆分函数，传入单个分段
    seg_first, seg_second = split_segment_func(
        segment_to_split,
        split_time=split_time,
        split_text_position=split_text_position,
        split_text_search=split_text
    )
    
    # 确保字段正确继承
    # 继承 translated_text、speaker_id 等字段
    for key in ['translated_text', 'speaker_id']:
        if key in segment_to_split:
            seg_first[key] = segment_to_split[key]
            seg_second[key] = segment_to_split[key]

    # 处理参考音频路径 - 根据时间戳切分原始音频
    # 优先使用 audio_path，如果没有则使用 reference_audio_path
    original_audio_path = segment_to_split.get('audio_path') or segment_to_split.get('reference_audio_path')
    if not original_audio_path or not os.path.exists(original_audio_path):
        # 如果 audio_path 不存在，尝试从 ref_audio 目录查找
        task_dir = _find_task_dir(task_id)
        if task_dir:
            ref_audio_dir = os.path.join(task_dir, "ref_audio")
            if os.path.exists(ref_audio_dir):
                ref_files = sorted([f for f in os.listdir(ref_audio_dir) if f.endswith('.wav')])
                if ref_files:
                    # 尝试使用对应 segment_id 的文件
                    original_segment_id = segment_to_split.get('id', segment_id)
                    expected_file = os.path.join(ref_audio_dir, f"06_ref_segment_{original_segment_id:03d}.wav")
                    if os.path.exists(expected_file):
                        original_audio_path = expected_file
                    else:
                        # 如果对应文件不存在，使用第一个可用文件
                        original_audio_path = os.path.join(ref_audio_dir, ref_files[0])

    # 构建新的分段列表
    new_segments = segments.copy()
    # 替换原分段为第一个新分段
    new_segments[segment_id] = seg_first
    # 在下一个位置插入第二个新分段
    new_segments.insert(segment_id + 1, seg_second)

    # 重新编号所有分段，确保ID连续
    # 这是必要的，因为前端依赖连续的ID进行显示和操作
    for i, segment in enumerate(new_segments):
        segment['id'] = i

    # 现在分段ID已经重新编号，可以切分音频了
    if original_audio_path and os.path.exists(original_audio_path):
        # 切分音频
        try:
            # 为第一个分段切分音频（根据实际时间戳）
            first_audio_path = _cut_audio_segment(
                original_audio_path,
                seg_first['start'],
                seg_first['end'],
                task_id,
                seg_first['id']
            )
            if first_audio_path:
                seg_first['audio_path'] = first_audio_path
                seg_first['reference_audio_path'] = first_audio_path

            # 为第二个分段切分音频（根据实际时间戳）
            second_audio_path = _cut_audio_segment(
                original_audio_path,
                seg_second['start'],
                seg_second['end'],
                task_id,
                seg_second['id']
            )
            if second_audio_path:
                seg_second['audio_path'] = second_audio_path
                seg_second['reference_audio_path'] = second_audio_path

            logger.info(f"成功为拆分后的分段切分音频: {segment_id} -> {seg_first['id']}, {seg_second['id']}")
        except Exception as e:
            logger.warning(f"音频切分失败，使用原始音频作为参考: {e}")
            # 切分失败时，回退到使用原始音频
            seg_first['reference_audio_path'] = original_audio_path
            seg_second['reference_audio_path'] = original_audio_path
    else:
        logger.warning(f"找不到原始音频文件用于切分: {original_audio_path}")
        # 如果找不到原始音频，设置为空，后续会使用默认音频

    # 两个新分段的克隆音频路径都设置为空（因为时间范围已改变，需要重新合成）
    seg_first['cloned_audio_path'] = None
    seg_second['cloned_audio_path'] = None
    
    # 重新命名受影响的音频文件（只重命名拆分点之后的分段）
    await _rename_audio_files_after_split(task_id, new_segments, segment_id)
    
    # 保存更新
    await update_segments(task_id, new_segments)
    
    return new_segments


async def delete_segments(task_id: str, segment_ids: List[int]) -> List[Dict[str, Any]]:
    """删除分段"""
    segments = await get_segments(task_id)
    
    # 按索引从大到小删除，避免索引变化
    for seg_id in sorted(segment_ids, reverse=True):
        if 0 <= seg_id < len(segments):
            segments.pop(seg_id)
    
    # 重新编号
    for i, segment in enumerate(segments):
        segment["id"] = i
    
    # 保存更新
    await update_segments(task_id, segments)
    
    return segments


async def regenerate_final_media(task_id: str):
    """重新生成最终音频和视频"""
    from app.services.audio_merge_service import incremental_merge_audio, incremental_merge_video
    from app.api.translation import tasks
    
    segments = await get_segments(task_id)
    await incremental_merge_audio(task_id, segments)
    result = await incremental_merge_video(task_id)
    
    # 更新任务状态中的 final_video_path
    if task_id in tasks and result.get("success"):
        final_video_path = result.get("video_path")
        if final_video_path and os.path.exists(final_video_path):
            tasks[task_id]["final_video_path"] = final_video_path
            logger.info(f"已更新任务状态中的 final_video_path: {final_video_path}")


def _find_task_dir(task_id: str) -> Optional[str]:
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

    # 如果任务状态中没有，尝试从文件系统中查找（回退方案）
    try:
        outputs_dir = Path("data/outputs")
        if outputs_dir.exists():
            # 首先尝试精确匹配task_id
            for dir_path in outputs_dir.iterdir():
                if dir_path.is_dir() and task_id in dir_path.name:
                    task_dir = str(dir_path)
                    logger.info(f"从文件系统找到任务目录: {task_dir}")
                    return task_dir

            # 如果找不到精确匹配，返回最新的任务目录（通常是用户当前编辑的）
            task_dirs = [d for d in outputs_dir.iterdir() if d.is_dir()]
            if task_dirs:
                # 按修改时间排序，返回最新的
                latest_dir = max(task_dirs, key=lambda d: d.stat().st_mtime)
                task_dir = str(latest_dir)
                logger.info(f"使用最新的任务目录作为回退: {task_dir}")
                return task_dir
    except Exception as e:
        logger.warning(f"从文件系统查找任务目录失败: {e}")

    # 如果都找不到，返回 None
    logger.error(f"任务 {task_id} 的目录不存在")
    return None


def find_task_dir(task_id: str) -> Optional[str]:
    """查找任务目录（公共函数）"""
    return _find_task_dir(task_id)


def _update_translation_file(task_dir: str, segments: List[Dict[str, Any]]):
    """更新翻译文件（05_translation.txt）"""
    translation_file = os.path.join(task_dir, "05_translation.txt")
    
    with open(translation_file, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments):
            start = segment.get("start", 0.0)
            end = segment.get("end", 0.0)
            text = segment.get("text", "")
            translated_text = segment.get("translated_text", text)
            speaker_id = segment.get("speaker_id")
            
            f.write(f"Segment {i+1} ({start:.3f}s - {end:.3f}s)")
            if speaker_id:
                f.write(f" [speaker: {speaker_id}]")
            f.write(":\n")
            f.write(f"原文: {text}\n")
            f.write(f"译文: {translated_text}\n\n")

