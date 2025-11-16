"""
语义分段器 - 基于标点符号的智能分段
将 Whisper 单词时间戳重新组织为语义完整的分段
"""

import logging
from typing import List, Dict, Any, Optional

class SemanticSegmenter:
    """语义分段器 - 基于标点符号进行智能分段"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化语义分段器
        
        Args:
            config: 配置字典
        """
        self.logger = logging.getLogger(__name__)
        segmentation_config = config.get("whisper", {}).get("segmentation", {})
        
        # 分段配置
        self.min_duration = segmentation_config.get("min_segment_duration", 3.0)
        self.max_duration = segmentation_config.get("max_segment_duration", 15.0)
        
        # 标点符号配置
        punctuation_config = segmentation_config.get("punctuation", {})
        self.sentence_marks = set(punctuation_config.get("marks", [".", "!", "?", "。", "！", "？"]))
        self.pause_marks = set([",", ";", ":", "，", "；", "："])  # 次级标点
        
        self.logger.info(f"语义分段器初始化: min={self.min_duration}s, max={self.max_duration}s")
    
    def segment(self, words: List[Dict[str, Any]], text: str, speaker_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        将单词列表重新分段为语义完整的分段
        
        Args:
            words: 单词列表，每个单词包含 word, start, end, probability
            text: 完整转录文本
            speaker_id: 说话人ID（可选，用于多说话人场景）
            
        Returns:
            分段列表，每个分段包含 start, end, text, words, speaker_id（如果提供）
        """
        if not words:
            self.logger.warning("单词列表为空，无法分段")
            return []
        
        self.logger.info(f"开始语义分段: {len(words)} 个单词")
        
        # 1. 识别句子边界
        sentence_boundaries = self._find_sentence_boundaries(words)
        self.logger.info(f"识别到 {len(sentence_boundaries)} 个句子边界")
        
        # 2. 根据边界创建初始分段
        segments = self._create_segments_from_boundaries(words, sentence_boundaries)
        self.logger.info(f"创建初始分段: {len(segments)} 个分段")
        
        # 3. 优化分段时长
        segments = self._optimize_segment_durations(segments, words)
        self.logger.info(f"优化后分段: {len(segments)} 个分段")
        
        # 4. 构建最终分段结构
        final_segments = self._build_final_segments(segments, words)
        
        self.logger.info(f"✅ 语义分段完成: {len(final_segments)} 个分段")
        return final_segments
    
    def _find_sentence_boundaries(self, words: List[Dict[str, Any]]) -> List[int]:
        """
        识别句子边界（句号、问号、感叹号等）
        
        Returns:
            单词索引列表，表示句子结束位置
        """
        boundaries = []
        for i, word in enumerate(words):
            word_text = word.get("word", "").strip()
            # 检查单词是否以句子结束标点结尾
            if any(word_text.endswith(mark) for mark in self.sentence_marks):
                boundaries.append(i)
        
        # 确保最后一个单词也是边界
        if boundaries and boundaries[-1] != len(words) - 1:
            boundaries.append(len(words) - 1)
        elif not boundaries:
            boundaries.append(len(words) - 1)
        
        return boundaries
    
    def _create_segments_from_boundaries(self, words: List[Dict[str, Any]], 
                                        boundaries: List[int]) -> List[Dict[str, Any]]:
        """
        根据句子边界创建初始分段
        
        Returns:
            分段列表，每个分段包含 start_idx, end_idx, duration
        """
        segments = []
        start_idx = 0
        
        for boundary_idx in boundaries:
            if boundary_idx >= start_idx:
                start_time = words[start_idx].get("start", 0)
                end_time = words[boundary_idx].get("end", 0)
                duration = end_time - start_time
                
                segments.append({
                    "start_idx": start_idx,
                    "end_idx": boundary_idx,
                    "duration": duration
                })
                
                start_idx = boundary_idx + 1
        
        return segments
    
    def _optimize_segment_durations(self, segments: List[Dict[str, Any]], 
                                    words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        优化分段时长，确保在 min_duration 和 max_duration 之间
        
        处理规则:
        1. 过短分段：合并到下一个分段
        2. 过长分段：在次级标点（逗号等）处强制分段
        """
        optimized = []
        i = 0
        
        while i < len(segments):
            segment = segments[i]
            duration = segment["duration"]
            
            # 情况1: 分段过短，尝试合并
            if duration < self.min_duration and i < len(segments) - 1:
                next_segment = segments[i + 1]
                merged_time = (words[next_segment["end_idx"]].get("end", 0) - 
                              words[segment["start_idx"]].get("start", 0))
                
                # 如果合并后不超过最大时长，则合并
                if merged_time <= self.max_duration:
                    optimized.append({
                        "start_idx": segment["start_idx"],
                        "end_idx": next_segment["end_idx"],
                        "duration": merged_time
                    })
                    i += 2  # 跳过下一个分段
                    continue
            
            # 情况2: 分段过长，在次级标点处强制分段
            if duration > self.max_duration:
                sub_segments = self._split_long_segment(segment, words)
                optimized.extend(sub_segments)
            else:
                optimized.append(segment)
            
            i += 1
        
        return optimized
    
    def _split_long_segment(self, segment: Dict[str, Any], 
                           words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        分割过长的分段，在次级标点（逗号等）处分段
        """
        start_idx = segment["start_idx"]
        end_idx = segment["end_idx"]
        
        # 查找次级标点位置
        pause_positions = []
        for i in range(start_idx, end_idx + 1):
            word_text = words[i].get("word", "").strip()
            if any(word_text.endswith(mark) for mark in self.pause_marks):
                pause_positions.append(i)
        
        # 如果没有次级标点，按时长强制分段
        if not pause_positions:
            return self._force_split_by_duration(segment, words)
        
        # 在次级标点处分段
        sub_segments = []
        sub_start = start_idx
        
        for pause_idx in pause_positions:
            sub_duration = (words[pause_idx].get("end", 0) - 
                           words[sub_start].get("start", 0))
            
            # 如果当前子分段达到合理长度，创建分段
            if sub_duration >= self.min_duration:
                sub_segments.append({
                    "start_idx": sub_start,
                    "end_idx": pause_idx,
                    "duration": sub_duration
                })
                sub_start = pause_idx + 1
        
        # 处理剩余部分
        if sub_start <= end_idx:
            remaining_duration = (words[end_idx].get("end", 0) - 
                                 words[sub_start].get("start", 0))
            sub_segments.append({
                "start_idx": sub_start,
                "end_idx": end_idx,
                "duration": remaining_duration
            })
        
        return sub_segments if sub_segments else [segment]
    
    def _force_split_by_duration(self, segment: Dict[str, Any], 
                                 words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        按时长强制分割分段（当没有合适的标点时）
        """
        start_idx = segment["start_idx"]
        end_idx = segment["end_idx"]
        sub_segments = []
        
        current_start = start_idx
        for i in range(start_idx, end_idx + 1):
            duration = (words[i].get("end", 0) - 
                       words[current_start].get("start", 0))
            
            if duration >= self.max_duration:
                sub_segments.append({
                    "start_idx": current_start,
                    "end_idx": i - 1,
                    "duration": words[i - 1].get("end", 0) - words[current_start].get("start", 0)
                })
                current_start = i
        
        # 添加最后一段
        if current_start <= end_idx:
            sub_segments.append({
                "start_idx": current_start,
                "end_idx": end_idx,
                "duration": words[end_idx].get("end", 0) - words[current_start].get("start", 0)
            })
        
        return sub_segments
    
    def _build_final_segments(self, segments: List[Dict[str, Any]], 
                             words: List[Dict[str, Any]], speaker_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        构建最终的分段结构
        
        Args:
            segments: 分段信息列表
            words: 单词列表（应使用全局时间戳）
            speaker_id: 说话人ID（可选）
        
        注意：如果单词间存在大的时间间隔（>1.5秒），会自动拆分分段
        """
        final_segments = []
        max_gap = 1.5  # 允许的最大时间间隔（秒），超过此值将拆分分段
        
        for i, seg in enumerate(segments):
            start_idx = seg["start_idx"]
            end_idx = seg["end_idx"]
            
            # 提取分段的单词
            segment_words = words[start_idx:end_idx + 1]
            
            if not segment_words:
                continue
            
            # 检查时间连续性，如果存在大的时间间隔，拆分分段
            continuous_groups = []
            current_group = [segment_words[0]]
            
            for j in range(1, len(segment_words)):
                prev_word = segment_words[j - 1]
                curr_word = segment_words[j]
                
                prev_end = prev_word.get("end", 0)
                curr_start = curr_word.get("start", 0)
                
                # 如果时间间隔过大，创建新的连续组
                if curr_start - prev_end > max_gap:
                    if current_group:
                        continuous_groups.append(current_group)
                    current_group = [curr_word]
                else:
                    current_group.append(curr_word)
            
            # 添加最后一组
            if current_group:
                continuous_groups.append(current_group)
            
            # 为每个连续组创建分段
            for group_idx, word_group in enumerate(continuous_groups):
                if not word_group:
                    continue
                
                # 构建分段文本
                segment_text = "".join(w.get("word", "") for w in word_group).strip()
                
                # 使用连续单词的时间范围（不包括静音段）
                start_time = word_group[0].get("start", 0)
                end_time = word_group[-1].get("end", 0)
                
                segment_dict = {
                    "id": len(final_segments),
                    "start": start_time,
                    "end": end_time,
                    "text": segment_text,
                    "words": word_group,
                    "seek": 0,  # 兼容性字段
                    "tokens": [],  # 兼容性字段
                    "temperature": 0.0,
                    "avg_logprob": 0.0,
                    "compression_ratio": 1.0,
                    "no_speech_prob": 0.0
                }
                # 保留speaker_id（如果提供）
                if speaker_id is not None:
                    segment_dict["speaker_id"] = speaker_id
                final_segments.append(segment_dict)
        
        return final_segments
