"""
分段编辑模块
提供分段文件的解析、验证和保存功能
支持用户手动调整分段（合并、拆分、调整时间戳等）
根据单词级时间戳自动计算分段时间戳
"""

import os
import json
import logging
from typing import Dict, Any, List, Tuple, Optional
from .output_manager import OutputManager, StepNumbers


logger = logging.getLogger(__name__)


def calculate_segment_timestamps_from_words(words: List[Dict[str, Any]]) -> Tuple[float, float]:
    """
    根据单词时间戳计算分段的开始和结束时间
    
    Args:
        words: 单词列表，每个单词包含 word, start, end, probability
    
    Returns:
        (start_time, end_time) 元组
    """
    if not words:
        return 0.0, 0.0
    
    start_time = min(word.get('start', 0.0) for word in words)
    end_time = max(word.get('end', 0.0) for word in words)
    
    return start_time, end_time


def rebuild_text_from_words(words: List[Dict[str, Any]]) -> str:
    """
    根据单词列表重建文本内容
    
    Args:
        words: 单词列表
    
    Returns:
        拼接后的文本
    """
    if not words:
        return ""
    
    return "".join(word.get('word', '') for word in words).strip()


def find_words_in_time_range(
    all_words: List[Dict[str, Any]], 
    start_time: float, 
    end_time: float
) -> List[Dict[str, Any]]:
    """
    在时间范围内查找对应的单词
    
    Args:
        all_words: 所有单词列表
        start_time: 开始时间
        end_time: 结束时间
    
    Returns:
        时间范围内的单词列表
    """
    result = []
    for word in all_words:
        word_start = word.get('start', 0.0)
        word_end = word.get('end', 0.0)
        
        # 检查单词是否与时间范围有重叠
        if word_start < end_time and word_end > start_time:
            result.append(word)
    
    return result


def validate_segment_data(
    segments: List[Dict[str, Any]], 
    all_words: Optional[List[Dict[str, Any]]] = None
) -> Tuple[bool, str]:
    """
    验证分段数据完整性
    
    Args:
        segments: 分段列表
        all_words: 所有单词列表（用于验证单词覆盖，可选）
    
    Returns:
        (是否有效, 错误信息)
    """
    if not segments:
        return False, "分段列表为空"
    
    # 检查分段是否按时间顺序排列
    for i in range(len(segments) - 1):
        current_end = float(segments[i].get('end', 0))
        next_start = float(segments[i + 1].get('start', 0))
        
        if current_end > next_start + 0.1:  # 允许0.1秒的误差
            return False, f"分段 {i+1} 和分段 {i+2} 时间戳重叠或顺序错误: " \
                         f"分段 {i+1} 结束于 {current_end:.3f}s, " \
                         f"分段 {i+2} 开始于 {next_start:.3f}s"
    
    # 检查每个分段的完整性
    for i, segment in enumerate(segments):
        start = float(segment.get('start', 0))
        end = float(segment.get('end', 0))
        text = segment.get('text', '').strip()
        words = segment.get('words', [])
        
        # 检查时间戳有效性
        if end <= start:
            return False, f"分段 {i+1} 时间戳无效: 结束时间 {end:.3f}s <= 开始时间 {start:.3f}s"
        
        # 检查文本是否为空
        if not text:
            return False, f"分段 {i+1} 文本为空"
        
        # 检查单词列表是否存在
        if not words:
            logger.warning(f"分段 {i+1} 缺少单词列表")
        else:
            # 验证文本与单词是否匹配
            words_text = rebuild_text_from_words(words)
            if words_text != text:
                logger.warning(f"分段 {i+1} 文本与单词不匹配: 文本='{text}', 单词文本='{words_text}'")
            
            # 验证时间戳与单词时间戳是否匹配
            word_start, word_end = calculate_segment_timestamps_from_words(words)
            if abs(word_start - start) > 0.1 or abs(word_end - end) > 0.1:
                logger.warning(f"分段 {i+1} 时间戳与单词时间戳不匹配: "
                             f"分段时间=({start:.3f}s - {end:.3f}s), "
                             f"单词时间=({word_start:.3f}s - {word_end:.3f}s)")
    
    # 如果提供了所有单词列表，检查单词覆盖
    if all_words:
        covered_words = set()
        for segment in segments:
            for word in segment.get('words', []):
                # 使用单词的start和end作为唯一标识
                word_key = (word.get('start', 0), word.get('end', 0), word.get('word', ''))
                covered_words.add(word_key)
        
        all_words_set = set()
        for word in all_words:
            word_key = (word.get('start', 0), word.get('end', 0), word.get('word', ''))
            all_words_set.add(word_key)
        
        missing_words = all_words_set - covered_words
        if missing_words:
            logger.warning(f"有 {len(missing_words)} 个单词未被任何分段包含")
    
    return True, ""


def normalize_segment(segment: Dict[str, Any], all_words: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    规范化分段数据，根据单词时间戳自动计算分段时间戳和文本
    
    Args:
        segment: 分段数据
        all_words: 所有单词列表（如果分段缺少words字段，则从all_words中查找）
    
    Returns:
        规范化后的分段数据
    """
    words = segment.get('words', [])
    
    # 如果分段缺少words字段，尝试从all_words中查找
    if not words and all_words:
        start_time = float(segment.get('start', 0))
        end_time = float(segment.get('end', 0))
        words = find_words_in_time_range(all_words, start_time, end_time)
        segment['words'] = words
    
    # 根据单词时间戳重新计算分段时间戳
    # 注意：只有在分段没有明确设置时间戳时才根据words重新计算
    # 这样可以保留用户手动编辑的时间戳
    if words:
        word_start, word_end = calculate_segment_timestamps_from_words(words)
        # 如果分段的时间戳与单词时间戳差异很大（>0.1秒），说明用户可能手动编辑过
        # 在这种情况下，保留用户编辑的时间戳，不覆盖
        existing_start = segment.get('start', 0)
        existing_end = segment.get('end', 0)
        
        # 如果时间戳差异不大，使用单词时间戳（更精确）
        # 如果差异很大，保留用户编辑的时间戳
        if abs(word_start - existing_start) < 0.1 and abs(word_end - existing_end) < 0.1:
            segment['start'] = word_start
            segment['end'] = word_end
        # 否则保留用户编辑的时间戳
        
        # 只有在segment没有text字段或text为空时，才根据单词重建文本
        # 这样可以保留用户编辑的文本内容
        existing_text = segment.get('text', '').strip()
        if not existing_text:
            # 根据单词重建文本
            words_text = rebuild_text_from_words(words)
            if words_text:
                segment['text'] = words_text
    
    return segment


def merge_segments(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    合并多个分段
    
    Args:
        segments: 要合并的分段列表（必须按时间顺序排列）
    
    Returns:
        合并后的分段
    """
    if not segments:
        raise ValueError("分段列表为空，无法合并")
    
    if len(segments) == 1:
        return segments[0].copy()
    
    # 合并所有单词
    all_words = []
    for seg in segments:
        all_words.extend(seg.get('words', []))
    
    # 按时间排序单词
    all_words.sort(key=lambda w: (w.get('start', 0), w.get('end', 0)))
    
    # 合并文本
    all_texts = [seg.get('text', '').strip() for seg in segments]
    merged_text = ' '.join(all_texts).strip()
    
    # 计算时间戳
    start_time = min(float(seg.get('start', 0)) for seg in segments)
    end_time = max(float(seg.get('end', 0)) for seg in segments)
    
    # 构建合并后的分段
    merged_segment = {
        'start': start_time,
        'end': end_time,
        'text': merged_text,
        'words': all_words,
    }
    
    # 保留speaker_id（如果所有分段都有相同的speaker_id）
    speaker_ids = [seg.get('speaker_id') for seg in segments if 'speaker_id' in seg]
    if speaker_ids and len(set(speaker_ids)) == 1:
        merged_segment['speaker_id'] = speaker_ids[0]
    
    # 保留其他字段
    for key in ['id', 'seek', 'tokens', 'temperature', 'avg_logprob', 'compression_ratio', 'no_speech_prob']:
        if key in segments[0]:
            merged_segment[key] = segments[0][key]
    
    return merged_segment


def split_segment(
    segment: Dict[str, Any], 
    split_time: Optional[float] = None,
    split_text_position: Optional[int] = None,
    split_text_search: Optional[str] = None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    拆分分段
    
    Args:
        segment: 要拆分的分段
        split_time: 拆分时间点（优先使用）
        split_text_position: 文本中的拆分位置（字符位置）
        split_text_search: 要搜索的文本片段（用于按文本位置拆分，优先于 split_text_position）
    
    Returns:
        (前半段, 后半段) 元组
    """
    words = segment.get('words', [])
    if not words:
        raise ValueError("分段缺少单词列表，无法拆分")
    
    # 确定拆分点
    if split_time is not None:
        # 根据时间拆分
        split_idx = None
        for i, word in enumerate(words):
            word_start = word.get('start', 0)
            word_end = word.get('end', 0)
            if word_start <= split_time <= word_end:
                split_idx = i + 1  # 在这个单词之后拆分
                break
            elif word_end > split_time:
                split_idx = i
                break
        
        if split_idx is None:
            # 如果没找到合适的位置，在中间拆分
            split_idx = len(words) // 2
    elif split_text_search is not None:
        # 根据搜索文本拆分（简单逻辑：直接在原始文本中搜索，找到后切分）
        text = segment.get('text', '')
        
        # 在原始文本中精确搜索（包括空格）
        pos = text.find(split_text_search)
        if pos == -1:
            # 增强错误提示，显示原始文本和用户输入的文本，帮助调试
            text_preview = text[:200] + "..." if len(text) > 200 else text
            search_preview = split_text_search[:200] + "..." if len(split_text_search) > 200 else split_text_search
            error_msg = (
                f"未找到匹配的文本片段：'{split_text_search}'\n\n"
                f"提示：请检查输入是否正确（包括空格），文本片段必须完全出现在分段文本中\n\n"
                f"原始分段文本（前200字符）：\n{repr(text_preview)}\n\n"
                f"您输入的文本（前200字符）：\n{repr(search_preview)}\n\n"
            )
            
            # 检查常见的字符差异
            if '﹔' in split_text_search and '﹔' not in text:
                if '；' in text:
                    error_msg += "可能的字符差异：原始文本使用'；'（全角分号），您输入的是'﹔'\n"
                elif ';' in text:
                    error_msg += "可能的字符差异：原始文本使用';'（半角分号），您输入的是'﹔'\n"
            elif '；' in split_text_search and '；' not in text:
                if '﹔' in text:
                    error_msg += "可能的字符差异：原始文本使用'﹔'，您输入的是'；'（全角分号）\n"
                elif ';' in text:
                    error_msg += "可能的字符差异：原始文本使用';'（半角分号），您输入的是'；'（全角分号）\n"
            
            raise ValueError(error_msg)
        
        # 找到搜索文本的结束位置
        split_text_end = pos + len(split_text_search)
        
        # 找到对应的单词索引（搜索文本结束位置对应的单词）
        # 遍历单词，找到包含 split_text_end 的单词，在该单词之后拆分
        split_idx = None
        search_start = 0
        
        for i, word in enumerate(words):
            word_text = word.get('word', '')
            if not word_text:
                continue
            
            # 在完整文本中查找当前单词的位置
            word_start = text.find(word_text, search_start)
            if word_start == -1:
                # 如果找不到，尝试忽略大小写
                word_start = text.lower().find(word_text.lower(), search_start)
                if word_start == -1:
                    # 如果还是找不到，跳过这个单词
                    continue
            
            word_end = word_start + len(word_text)
            
            # 检查 split_text_end 是否在当前单词的范围内或之后
            # 如果 split_text_end 正好等于 word_start，在前一个单词之后拆分
            if split_text_end == word_start:
                # 位置正好等于单词开始位置，在前一个单词之后拆分
                if i > 0:
                    split_idx = i
                else:
                    split_idx = 1
                break
            elif word_start < split_text_end <= word_end:
                # 位置在单词范围内，在该单词之后拆分
                split_idx = i + 1
                break
            elif split_text_end < word_start:
                # 位置在当前单词之前，在前一个单词之后拆分
                if i > 0:
                    split_idx = i
                else:
                    split_idx = 1
                break
            
            # 更新搜索起始位置，避免重复查找
            search_start = word_end
        
        if split_idx is None:
            # 如果没找到，在最后一个单词之后拆分
            split_idx = len(words)
    elif split_text_position is not None:
        # 根据文本位置拆分（直接基于字符位置，不依赖单词边界）
        text = segment.get('text', '')
        if split_text_position < 0:
            split_text_position = 0
        if split_text_position >= len(text):
            split_text_position = len(text) // 2
        
        # 找到最接近 split_text_position 的单词边界
        # 优先选择在单词之间的空格位置拆分
        split_idx = None
        prev_word_end = 0
        
        for i, word in enumerate(words):
            word_text = word.get('word', '').strip()  # 移除单词前后的空格
            if not word_text:
                continue
            
            # 在文本中查找单词（忽略前导空格）
            word_start = text.find(word_text, prev_word_end)
            if word_start == -1:
                # 如果找不到，尝试忽略大小写
                word_start = text.lower().find(word_text.lower(), prev_word_end)
                if word_start == -1:
                    continue
            
            word_end = word_start + len(word_text)
            
            # 检查光标位置是否在当前单词范围内
            if word_start <= split_text_position < word_end:
                # 光标在单词内部，检查是否更接近单词开始还是结束
                if split_text_position - word_start < word_end - split_text_position:
                    # 更接近单词开始，在前一个单词之后拆分
                    split_idx = i
                else:
                    # 更接近单词结束，在当前单词之后拆分
                    split_idx = i + 1
                break
            elif split_text_position < word_start:
                # 光标在单词之前，检查是否在单词间空格中
                if prev_word_end <= split_text_position < word_start:
                    # 在单词间空格中，在前一个单词之后拆分
                        split_idx = i
                break
            
            prev_word_end = word_end
        
        # 如果没找到合适的位置，默认在中间拆分
        if split_idx is None:
            split_idx = len(words) // 2
    else:
        # 默认在中间拆分
        split_idx = len(words) // 2
    
    # 拆分单词列表
    words_first = words[:split_idx]
    words_second = words[split_idx:]
    
    if not words_first or not words_second:
        raise ValueError("拆分后某个分段为空")
    
    # 构建前半段
    start_time_first, end_time_first = calculate_segment_timestamps_from_words(words_first)
    
    # 如果使用 split_text_search，第一段的文本直接使用搜索文本（完全匹配）
    if split_text_search is not None:
        text_first = split_text_search
    else:
        text_first = rebuild_text_from_words(words_first)
    
    segment_first = {
        'start': start_time_first,
        'end': end_time_first,
        'text': text_first,
        'words': words_first,
    }
    
    # 构建后半段
    start_time_second, end_time_second = calculate_segment_timestamps_from_words(words_second)
    
    # 如果使用 split_text_search，第二段的文本使用剩余部分
    if split_text_search is not None:
        text = segment.get('text', '')
        pos = text.find(split_text_search)
        if pos != -1:
            split_text_end = pos + len(split_text_search)
            text_second = text[split_text_end:].lstrip()  # 剩余文本，去掉前导空格
        else:
            text_second = rebuild_text_from_words(words_second)
    else:
        text_second = rebuild_text_from_words(words_second)
    
    segment_second = {
        'start': start_time_second,
        'end': end_time_second,
        'text': text_second,
        'words': words_second,
    }
    
    # 保留speaker_id和其他字段
    if 'speaker_id' in segment:
        segment_first['speaker_id'] = segment['speaker_id']
        segment_second['speaker_id'] = segment['speaker_id']
    
    # 保留技术字段
    for key in ['id', 'seek', 'tokens', 'temperature', 'avg_logprob', 'compression_ratio', 'no_speech_prob']:
        if key in segment:
            segment_first[key] = segment[key]
            segment_second[key] = segment[key]
    
    # 保留用户数据字段（这些字段会在服务层进一步处理）
    # translated_text、reference_audio_path 等会在服务层继承
    # audio_path 和 cloned_audio_path 会在服务层设置为 None
    
    return segment_first, segment_second


def load_segments(file_path: str) -> List[Dict[str, Any]]:
    """
    从JSON文件加载分段数据
    
    Args:
        file_path: JSON文件路径
    
    Returns:
        分段列表
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"分段文件不存在: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        segments = json.load(f)
    
    if not isinstance(segments, list):
        raise ValueError(f"分段文件格式错误: 期望列表，得到 {type(segments)}")
    
    logger.info(f"从 {file_path} 加载了 {len(segments)} 个分段")
    return segments


def save_segments(
    segments: List[Dict[str, Any]], 
    output_manager: OutputManager,
    all_words: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, str]:
    """
    保存分段数据到JSON和TXT文件
    
    Args:
        segments: 分段列表
        output_manager: OutputManager实例
        all_words: 所有单词列表（用于验证，可选）
    
    Returns:
        包含保存的文件路径的字典
    """
    # 规范化所有分段
    normalized_segments = []
    for i, segment in enumerate(segments):
        normalized_seg = normalize_segment(segment.copy(), all_words)
        # 更新id
        normalized_seg['id'] = i
        normalized_segments.append(normalized_seg)
    
    # 验证数据
    is_valid, error_msg = validate_segment_data(normalized_segments, all_words)
    if not is_valid:
        logger.warning(f"分段数据验证警告: {error_msg}")
        # 不抛出异常，允许用户保存不完美的数据
    
    # 保存 JSON 格式
    segments_json_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
    with open(segments_json_file, 'w', encoding='utf-8') as f:
        json.dump(normalized_segments, f, ensure_ascii=False, indent=2)
    
    # 保存 TXT 格式（可读格式）
    segments_txt_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_txt")
    with open(segments_txt_file, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(normalized_segments):
            start = segment.get('start', 0)
            end = segment.get('end', 0)
            text = segment.get('text', '')
            
            speaker_info = ""
            if 'speaker_id' in segment:
                speaker_info = f" [speaker: {segment['speaker_id']}]"
            
            f.write(f"Segment {i+1} ({start:.3f}s - {end:.3f}s){speaker_info}:\n")
            f.write(f"{text}\n\n")
    
    logger.info(f"分段文件已保存: {segments_json_file} 和 {segments_txt_file}")
    
    return {
        "segments_json_file": segments_json_file,
        "segments_txt_file": segments_txt_file
    }

