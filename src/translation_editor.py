"""
翻译文本编辑模块
提供解析、验证和保存翻译文本的功能
只允许修改译文，原文和时间戳等字段必须保持不变
"""

import os
import json
import re
import logging
from typing import Dict, Any, List, Tuple, Optional
from .output_manager import OutputManager, StepNumbers


logger = logging.getLogger(__name__)


def parse_translation_txt(file_path: str, original_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    解析 05_translation.txt 文件格式
    只提取译文部分，其他字段（时间戳、原文、speaker_id等）从 original_segments 获取
    
    Args:
        file_path: 翻译文本文件路径
        original_segments: 原始segments数据（包含时间戳、原文等）
    
    Returns:
        包含翻译后的segments列表
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"翻译文件不存在: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 解析格式：Segment {i+1} ({start:.3f}s - {end:.3f}s) [speaker: ...]:\n原文: {original_text}\n译文: {translated_text}\n\n
    # 支持可选的 [speaker: ...] 部分
    pattern = r'Segment\s+(\d+)\s+\(([\d.]+)s\s+-\s+([\d.]+)s\)(?:\s+\[speaker:[^\]]+\])?:\s*\n原文:\s*(.+?)\s*\n译文:\s*(.+?)(?=\n\nSegment|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    if len(matches) != len(original_segments):
        raise ValueError(
            f"段数不匹配: 解析到 {len(matches)} 段，但原始数据有 {len(original_segments)} 段"
        )
    
    translated_segments = []
    for i, (segment_num, start_str, end_str, original_text_from_file, translated_text) in enumerate(matches):
        original_segment = original_segments[i]
        
        # 验证时间戳是否匹配
        start_expected = float(original_segment['start'])
        end_expected = float(original_segment['end'])
        start_parsed = float(start_str)
        end_parsed = float(end_str)
        
        if abs(start_parsed - start_expected) > 0.001 or abs(end_parsed - end_expected) > 0.001:
            raise ValueError(
                f"段 {i+1} 时间戳不匹配: "
                f"期望 ({start_expected:.3f}s - {end_expected:.3f}s), "
                f"但文件中有 ({start_parsed:.3f}s - {end_parsed:.3f}s)"
            )
        
        # 验证原文是否匹配
        original_text_expected = original_segment.get('text', '').strip()
        original_text_from_file = original_text_from_file.strip()
        
        if original_text_expected != original_text_from_file:
            raise ValueError(
                f"段 {i+1} 原文不匹配:\n"
                f"期望: {original_text_expected}\n"
                f"文件: {original_text_from_file}"
            )
        
        # 构建翻译后的segment，只更新 translated_text 字段
        translated_segment = {
            'start': original_segment['start'],
            'end': original_segment['end'],
            'text': original_segment.get('text', ''),
            'original_text': original_segment.get('text', ''),
            'translated_text': translated_text.strip(),
            'words': original_segment.get('words', []),
        }
        
        # 保留speaker_id（如果存在）
        if 'speaker_id' in original_segment:
            translated_segment['speaker_id'] = original_segment['speaker_id']
        
        translated_segments.append(translated_segment)
    
    return translated_segments


def validate_translation_data(
    segments: List[Dict[str, Any]], 
    original_segments: List[Dict[str, Any]]
) -> Tuple[bool, str]:
    """
    验证翻译数据
    确保原文和时间戳未被修改，只允许修改译文
    
    Args:
        segments: 翻译后的segments
        original_segments: 原始segments
    
    Returns:
        (是否有效, 错误信息)
    """
    if len(segments) != len(original_segments):
        return False, f"段数不匹配: 翻译数据有 {len(segments)} 段，但原始数据有 {len(original_segments)} 段"
    
    for i, (translated_seg, original_seg) in enumerate(zip(segments, original_segments)):
        # 检查时间戳是否完全匹配
        start_translated = float(translated_seg.get('start', 0))
        end_translated = float(translated_seg.get('end', 0))
        start_original = float(original_seg.get('start', 0))
        end_original = float(original_seg.get('end', 0))
        
        if abs(start_translated - start_original) > 0.001:
            return False, f"段 {i+1} 的开始时间戳被修改: 原始 {start_original:.3f}s, 翻译数据 {start_translated:.3f}s"
        
        if abs(end_translated - end_original) > 0.001:
            return False, f"段 {i+1} 的结束时间戳被修改: 原始 {end_original:.3f}s, 翻译数据 {end_translated:.3f}s"
        
        # 检查原文是否完全匹配
        original_text_translated = translated_seg.get('original_text', '').strip()
        original_text_original = original_seg.get('text', '').strip()
        
        if original_text_translated != original_text_original:
            return False, f"段 {i+1} 的原文被修改:\n原始: {original_text_original}\n翻译数据: {original_text_translated}"
        
        # 检查译文是否存在
        if 'translated_text' not in translated_seg or not translated_seg['translated_text'].strip():
            return False, f"段 {i+1} 缺少译文或译文为空"
        
        # 检查speaker_id是否匹配（如果存在）
        if 'speaker_id' in original_seg:
            if translated_seg.get('speaker_id') != original_seg['speaker_id']:
                return False, f"段 {i+1} 的speaker_id被修改: 原始 {original_seg['speaker_id']}, 翻译数据 {translated_seg.get('speaker_id')}"
    
    return True, ""


def save_translation_files(
    segments: List[Dict[str, Any]], 
    output_manager: OutputManager,
    original_segments: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, str]:
    """
    同时保存翻译结果到 txt 和 json 文件
    
    Args:
        segments: 翻译后的segments
        output_manager: OutputManager实例
        original_segments: 原始segments（用于验证，可选）
    
    Returns:
        包含保存的文件路径的字典
    """
    # 验证数据（如果提供了原始segments）
    if original_segments:
        is_valid, error_msg = validate_translation_data(segments, original_segments)
        if not is_valid:
            raise ValueError(f"翻译数据验证失败: {error_msg}")
    
    # 保存 JSON 格式（供步骤6使用）
    translated_segments_file = os.path.join(output_manager.task_dir, "05_translated_segments.json")
    with open(translated_segments_file, 'w', encoding='utf-8') as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    
    # 保存 TXT 格式（可读格式）
    translation_file = output_manager.get_file_path(StepNumbers.STEP_5, "translation")
    with open(translation_file, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments):
            start = segment.get('start', 0)
            end = segment.get('end', 0)
            original_text = segment.get('original_text', segment.get('text', ''))
            translated_text = segment.get('translated_text', '')
            
            speaker_info = ""
            if 'speaker_id' in segment:
                speaker_info = f" [speaker: {segment['speaker_id']}]"
            
            f.write(f"Segment {i+1} ({start:.3f}s - {end:.3f}s){speaker_info}:\n")
            f.write(f"原文: {original_text}\n")
            f.write(f"译文: {translated_text}\n\n")
    
    logger.info(f"翻译文件已保存: {translation_file} 和 {translated_segments_file}")
    
    return {
        "translation_file": translation_file,
        "translated_segments_file": translated_segments_file
    }

