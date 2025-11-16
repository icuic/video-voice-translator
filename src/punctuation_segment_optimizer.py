"""
基于标点符号的分段优化器

功能:
- 根据标点符号(句号、问号、感叹号等)将语音识别结果分段
- 智能合并过短的分段 (< 3秒)
- 拆分过长的分段 (> 15秒)
- 控制字符长度范围 (20-200字符)
- 结合单词级时间戳精确计算分段时间

适用场景:
- 标点符号明确的书面语言
- 中文、英文等正式语音内容
- 需要保持语义完整性的翻译场景

参数配置:
- min_segment_duration: 最小分段时长(秒)
- max_segment_duration: 最大分段时长(秒)
- punctuation_marks: 分段标点符号列表
- min_segment_length: 最小字符长度
- max_segment_length: 最大字符长度
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
import os
import json

class PunctuationSegmentOptimizer:
    """基于标点符号的分段优化器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化分段优化器"""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 从配置中正确读取参数
        whisper_config = config.get("whisper", {})
        segmentation_config = whisper_config.get("segmentation", {})
        punctuation_config = segmentation_config.get("punctuation", {})
        
        # 分段时长参数
        self.min_segment_duration = segmentation_config.get("min_segment_duration", 3.0)
        self.max_segment_duration = segmentation_config.get("max_segment_duration", 15.0)
        
        # 标点符号分段参数
        self.punctuation_marks = punctuation_config.get("marks", ['.', '!', '?', '。', '！', '？'])
        self.min_segment_length = punctuation_config.get("min_segment_length", 20)
        self.max_segment_length = punctuation_config.get("max_segment_length", 200)
        
        self.logger.info("基于标点符号的分段优化器初始化完成")
        self.logger.info(f"最小分段时长: {self.min_segment_duration}秒")
        self.logger.info(f"最大分段时长: {self.max_segment_duration}秒")
        self.logger.info(f"标点符号: {self.punctuation_marks}")
        self.logger.info(f"最小分段长度: {self.min_segment_length}字符")
        self.logger.info(f"最大分段长度: {self.max_segment_length}字符")
    
    def optimize_segments(self, transcription_file: str, word_timestamps: List[Dict[str, Any]], speaker_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        使用基于标点符号的方法优化分段结果
        
        Args:
            transcription_file: 转录文本文件路径
            word_timestamps: 单词级别的时间戳列表
            speaker_id: 说话人ID（可选，用于多说话人场景）
            
        Returns:
            优化后的分段结果（保留speaker_id字段）
        """
        self.logger.info(f"开始基于标点符号优化分段，转录文件: {transcription_file}")
        self.logger.info(f"单词时间戳数量: {len(word_timestamps)}")
        
        # 处理边界情况
        if not word_timestamps:
            self.logger.error("单词时间戳列表为空")
            return []
        
        # 验证时间戳数据
        if not self._validate_word_timestamps(word_timestamps):
            self.logger.error("单词时间戳数据无效")
            return []
        
        # 读取完整转录文本
        full_text = self._read_transcription_file(transcription_file)
        if not full_text:
            self.logger.error("无法读取转录文件")
            return []
        
        self.logger.info(f"转录文本长度: {len(full_text)} 字符")
        
        # 基于标点符号分段
        text_segments = self._split_by_punctuation(full_text)
        self.logger.info(f"标点符号分段完成，得到 {len(text_segments)} 个文本分段")
        
        # 处理空分段
        text_segments = [seg for seg in text_segments if seg.strip()]
        if not text_segments:
            self.logger.warning("分段后没有有效文本")
            return []
        
        # 计算时间戳
        optimized_segments = self._calculate_timestamps(text_segments, word_timestamps, speaker_id)
        self.logger.info(f"时间戳计算完成，得到 {len(optimized_segments)} 个优化分段")
        
        # 验证分段数据
        optimized_segments = self._validate_segments(optimized_segments)
        
        # 长度控制优化
        final_segments = self._control_segment_length(optimized_segments)
        self.logger.info(f"长度控制完成，最终得到 {len(final_segments)} 个分段")
        
        return final_segments
    
    def _validate_word_timestamps(self, word_timestamps: List[Dict[str, Any]]) -> bool:
        """验证单词时间戳数据的有效性"""
        if not word_timestamps:
            return False
        
        for i, word_info in enumerate(word_timestamps):
            if not isinstance(word_info, dict):
                self.logger.error(f"单词时间戳 {i} 不是字典类型")
                return False
            
            if 'word' not in word_info:
                self.logger.error(f"单词时间戳 {i} 缺少 'word' 字段")
                return False
            
            if 'start' not in word_info or 'end' not in word_info:
                self.logger.error(f"单词时间戳 {i} 缺少时间戳字段")
                return False
            
            try:
                start_time = float(word_info['start'])
                end_time = float(word_info['end'])
                
                if start_time < 0 or end_time < 0:
                    self.logger.error(f"单词时间戳 {i} 时间值为负数")
                    return False
                
                if start_time > end_time:
                    self.logger.error(f"单词时间戳 {i} 开始时间大于结束时间")
                    return False
                
            except (ValueError, TypeError):
                self.logger.error(f"单词时间戳 {i} 时间值无效")
                return False
        
        return True
    
    def _validate_segments(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证和修复分段数据"""
        valid_segments = []
        
        for i, segment in enumerate(segments):
            if not isinstance(segment, dict):
                self.logger.warning(f"分段 {i} 不是字典类型，跳过")
                continue
            
            # 检查必要字段
            if 'start' not in segment or 'end' not in segment or 'text' not in segment:
                self.logger.warning(f"分段 {i} 缺少必要字段，跳过")
                continue
            
            # 验证时间戳
            try:
                start_time = float(segment['start'])
                end_time = float(segment['end'])
                
                if start_time < 0 or end_time < 0:
                    self.logger.warning(f"分段 {i} 时间值为负数，修复为0")
                    start_time = max(0, start_time)
                    end_time = max(0, end_time)
                
                if start_time > end_time:
                    self.logger.warning(f"分段 {i} 开始时间大于结束时间，交换时间戳")
                    start_time, end_time = end_time, start_time
                
                # 更新分段数据
                segment['start'] = start_time
                segment['end'] = end_time
                
            except (ValueError, TypeError):
                self.logger.warning(f"分段 {i} 时间戳无效，跳过")
                continue
            
            # 验证文本
            if not segment['text'] or not segment['text'].strip():
                self.logger.warning(f"分段 {i} 文本为空，跳过")
                continue
            
            valid_segments.append(segment)
        
        return valid_segments
    
    def _read_transcription_file(self, file_path: str) -> str:
        """读取转录文本文件"""
        try:
            self.logger.info(f"尝试读取转录文件: {file_path}")
            if not os.path.exists(file_path):
                self.logger.error(f"转录文件不存在: {file_path}")
                return ""
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                self.logger.info(f"成功读取转录文件，内容长度: {len(content)} 字符")
                return content
        except Exception as e:
            self.logger.error(f"读取转录文件失败: {e}")
            return ""
    
    def _split_by_punctuation(self, text: str) -> List[str]:
        """基于标点符号的基础分段"""
        segments = []
        current_segment = ""
        
        # 使用正则表达式分割，保留标点符号
        # 只支持真正的句子结束标点符号：. ! ? 。 ！ ？
        # 注意：逗号不应该作为句子结束的标志
        parts = re.split(r'([。！？\.\!\?])', text)
        
        for i, part in enumerate(parts):
            if not part.strip():
                continue
                
            current_segment += part
            
            # 检查是否是句子结束标点符号（不包括逗号）
            if part in self.punctuation_marks:
                # 确保分段不为空
                if current_segment.strip():
                    segments.append(current_segment.strip())
                    current_segment = ""
        
        # 处理剩余部分
        if current_segment.strip():
            segments.append(current_segment.strip())
        
        return segments if segments else [text]
    
    def _protect_abbreviations(self, text: str) -> str:
        """保护缩写词和特殊格式，避免被错误分割"""
        # 保护域名
        text = re.sub(r'(\w+)\.ai\b', r'\1_DOT_ai', text)
        text = re.sub(r'(\w+)\.com\b', r'\1_DOT_com', text)
        text = re.sub(r'(\w+)\.org\b', r'\1_DOT_org', text)
        text = re.sub(r'(\w+)\.net\b', r'\1_DOT_net', text)
        
        # 保护常见缩写
        text = re.sub(r'(\w+)\.(\w+)\b', r'\1_DOT_\2', text)  # 通用缩写模式
        
        # 保护数字中的小数点
        text = re.sub(r'(\d+)\.(\d+)', r'\1_DOT_\2', text)
        
        # 保护版本号
        text = re.sub(r'v(\d+)\.(\d+)', r'v\1_DOT_\2', text)
        
        return text
    
    def _is_sentence_end(self, text: str, pos: int) -> bool:
        """判断当前位置是否是真正的句子结束"""
        if pos >= len(text) - 1:
            return True
        
        # 检查下一个字符
        next_char = text[pos + 1]
        
        # 如果下一个字符是空格且再下一个字符是大写字母，很可能是句子结束
        if next_char == ' ' and pos + 2 < len(text):
            next_next_char = text[pos + 2]
            if next_next_char.isupper():
                return True
        
        # 如果下一个字符是换行符或结束符，是句子结束
        if next_char in ['\n', '\r']:
            return True
        
        # 如果当前位置是问号或感叹号，通常是句子结束
        if text[pos] in ['!', '?', '！', '？']:
            return True
        
        return False
    
    def _restore_abbreviations(self, text: str) -> str:
        """恢复被保护的缩写词"""
        # 恢复域名
        text = re.sub(r'(\w+)_DOT_ai\b', r'\1.ai', text)
        text = re.sub(r'(\w+)_DOT_com\b', r'\1.com', text)
        text = re.sub(r'(\w+)_DOT_org\b', r'\1.org', text)
        text = re.sub(r'(\w+)_DOT_net\b', r'\1.net', text)
        
        # 恢复通用缩写
        text = re.sub(r'(\w+)_DOT_(\w+)\b', r'\1.\2', text)
        
        # 恢复数字中的小数点
        text = re.sub(r'(\d+)_DOT_(\d+)', r'\1.\2', text)
        
        # 恢复版本号
        text = re.sub(r'v(\d+)_DOT_(\d+)', r'v\1.\2', text)
        
        return text
    
    def _calculate_timestamps(self, text_segments: List[str], word_timestamps: List[Dict[str, Any]], speaker_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """修复版本：改进的时间戳计算算法，确保覆盖完整的时间范围"""
        optimized_segments = []
        word_index = 0
        
        for i, segment_text in enumerate(text_segments):
            if word_index >= len(word_timestamps):
                self.logger.warning(f"分段 {i+1} 无法匹配：单词索引超出范围")
                break
            
            # 使用修复版本的匹配算法，避免跨分段匹配
            matched_words = self._find_matching_words_within_segments(segment_text, word_timestamps, word_index)
            
            if matched_words:
                # 计算完整的时间戳范围
                segment_start_time = matched_words[0].get('start', 0.0)
                segment_end_time = matched_words[-1].get('end', segment_start_time)
                
                # 验证时间戳的合理性
                if segment_end_time <= segment_start_time:
                    self.logger.warning(f"分段 {i+1} 时间戳异常，修复中...")
                    segment_end_time = segment_start_time + 1.0
                
                # 检查是否与其他分段重叠
                if optimized_segments:
                    prev_segment = optimized_segments[-1]
                    prev_end = prev_segment.get('end', 0)
                    if segment_start_time < prev_end:
                        self.logger.warning(f"分段 {i+1} 与前一分段重叠，调整时间戳")
                        segment_start_time = prev_end + 0.01
                
                segment_dict = {
                    'start': segment_start_time,
                    'end': segment_end_time,
                    'text': segment_text,
                    'words': matched_words
                }
                # 保留speaker_id（如果提供）
                if speaker_id is not None:
                    segment_dict['speaker_id'] = speaker_id
                optimized_segments.append(segment_dict)
                
                # 更新word_index到匹配结束的位置，避免重复匹配
                word_index += len(matched_words)
                self.logger.debug(f"分段 {i+1} 匹配完成，时间戳: {segment_start_time:.2f}s - {segment_end_time:.2f}s，word_index 更新为 {word_index}")
            else:
                # 如果无法匹配，使用当前位置的单词
                if word_index < len(word_timestamps):
                    word_info = word_timestamps[word_index]
                    segment_dict = {
                        'start': word_info.get('start', 0.0),
                        'end': word_info.get('end', word_info.get('start', 0.0) + 1.0),
                        'text': segment_text,
                        'words': [word_info]
                    }
                    # 保留speaker_id（如果提供）
                    if speaker_id is not None:
                        segment_dict['speaker_id'] = speaker_id
                    optimized_segments.append(segment_dict)
                    word_index += 1
                    self.logger.debug(f"分段 {i+1} 使用单个单词，word_index 更新为 {word_index}")
                else:
                    self.logger.warning(f"分段 {i+1} 无法匹配且单词索引超出范围")
        
        # 后处理：检查并修复时间戳重叠
        optimized_segments = self._fix_timestamp_overlaps(optimized_segments)
        
        # 最终验证：检查分段时间戳的合理性
        optimized_segments = self._validate_segment_timestamps(optimized_segments)
        
        return optimized_segments
    
    def _fix_timestamp_overlaps(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """修复时间戳重叠问题"""
        if len(segments) < 2:
            return segments
        
        fixed_segments = []
        for i, segment in enumerate(segments):
            if i == 0:
                fixed_segments.append(segment)
                continue
            
            prev_segment = fixed_segments[-1]
            current_segment = segment.copy()
            
            # 检查是否有重叠
            prev_end = prev_segment.get('end', 0)
            current_start = current_segment.get('start', 0)
            
            if current_start <= prev_end:
                # 有重叠，调整当前分段的起始时间
                new_start = prev_end + 0.01  # 添加0.01秒的间隔
                current_segment['start'] = new_start
                
                # 如果调整后结束时间小于起始时间，使用原始结束时间
                if current_segment.get('end', 0) <= new_start:
                    current_segment['end'] = new_start + 1.0  # 至少1秒时长
                
                self.logger.warning(f"修复分段 {i+1} 时间戳重叠: {current_start:.2f}s -> {new_start:.2f}s")
            
            fixed_segments.append(current_segment)
        
        return fixed_segments
    
    def _validate_segment_timestamps(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证和修复分段时间戳"""
        if not segments:
            return segments
        
        fixed_segments = []
        for i, segment in enumerate(segments):
            start_time = segment.get('start', 0)
            end_time = segment.get('end', 0)
            duration = end_time - start_time
            
            # 检查分段时长是否合理
            if duration < 0.5:  # 分段太短
                self.logger.warning(f"分段 {i+1} 过短 ({duration:.2f}s)，尝试修复")
                # 尝试从单词时间戳中获取更准确的时间
                words = segment.get('words', [])
                if words:
                    start_time = words[0].get('start', start_time)
                    end_time = words[-1].get('end', end_time)
                    duration = end_time - start_time
                    
                    if duration < 0.5:  # 仍然太短，使用默认时长
                        end_time = start_time + 2.0
                        self.logger.warning(f"分段 {i+1} 使用默认时长 2.0s")
            
            # 检查是否与前一分段重叠
            if fixed_segments:
                prev_end = fixed_segments[-1].get('end', 0)
                if start_time < prev_end:
                    start_time = prev_end + 0.01
                    self.logger.warning(f"分段 {i+1} 修复重叠问题")
            
            segment['start'] = start_time
            segment['end'] = end_time
            fixed_segments.append(segment)
        
        return fixed_segments
    
    def _find_matching_words(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """修复版本：找到与文本分段匹配的单词时间戳，确保匹配所有相关的Whisper分段"""
        if start_index >= len(word_timestamps):
            return []
        
        # 处理边界情况
        if not segment_text or not segment_text.strip():
            return []
        
        # 清理文本，移除多余空格
        clean_text = ' '.join(segment_text.split())
        
        # 使用更智能的语言检测
        language_type = self._detect_text_language(clean_text)
        
        if language_type == "chinese":
            return self._match_chinese_segment_fixed(clean_text, word_timestamps, start_index)
        elif language_type == "english":
            return self._match_english_segment_fixed(clean_text, word_timestamps, start_index)
        else:
            # 中英文混合文本，使用混合匹配策略
            return self._match_mixed_segment_fixed(clean_text, word_timestamps, start_index)
    
    def _detect_text_language(self, text: str) -> str:
        """更智能的语言检测，支持中英文混合文本"""
        if not text:
            return "unknown"
        
        # 统计中英文字符数量
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        total_chars = len(re.sub(r'[^\w\u4e00-\u9fff]', '', text))  # 排除标点符号和空格
        
        if total_chars == 0:
            return "unknown"
        
        # 计算比例
        chinese_ratio = chinese_chars / total_chars
        english_ratio = english_chars / total_chars
        
        # 判断语言类型
        if chinese_ratio > 0.7:
            return "chinese"
        elif english_ratio > 0.7:
            return "english"
        else:
            return "mixed"  # 中英文混合
    
    def _match_mixed_segment(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """处理中英文混合文本的匹配算法"""
        matched_words = []
        current_index = start_index
        
        # 将文本按中英文分割
        text_parts = self._split_mixed_text(segment_text)
        
        for part in text_parts:
            if not part.strip():
                continue
            
            # 检测每个部分的语言类型
            part_language = self._detect_text_language(part)
            
            if part_language == "chinese":
                # 使用中文匹配算法
                part_matched = self._match_chinese_segment(part, word_timestamps, current_index)
            elif part_language == "english":
                # 使用英文匹配算法
                part_matched = self._match_english_segment(part, word_timestamps, current_index)
            else:
                # 混合部分，使用更宽松的匹配
                part_matched = self._match_flexible_segment(part, word_timestamps, current_index)
            
            if part_matched:
                matched_words.extend(part_matched)
                current_index += len(part_matched)
            else:
                # 如果匹配失败，尝试跳过一些单词
                current_index += 1
                if current_index >= len(word_timestamps):
                    break
        
        return matched_words
    
    def _match_chinese_segment_fixed(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """修复版本：中文分段匹配算法，确保匹配所有相关的Whisper分段"""
        matched_words = []
        current_index = start_index
        
        # 清理分段文本
        clean_segment = segment_text.strip()
        if not clean_segment:
            return matched_words
        
        # 将文本转换为字符列表
        text_chars = list(clean_segment)
        char_index = 0
        max_chars = len(text_chars)
        
        self.logger.debug(f"修复版本：开始匹配中文分段: '{clean_segment[:50]}...'")
        self.logger.debug(f"分段字符数: {max_chars}, 起始索引: {start_index}")
        
        while current_index < len(word_timestamps) and char_index < max_chars:
            word_info = word_timestamps[current_index]
            word_text = word_info.get('word', '').strip()
            
            if not word_text:
                current_index += 1
                continue
            
            # 检查是否是时间跳跃（新的Whisper分段）
            if self._is_time_jump(word_timestamps, current_index):
                # 发现时间跳跃，说明进入了新的Whisper分段
                # 继续匹配，但记录时间跳跃
                matched_words.append(word_info)
                current_index += 1
                self.logger.debug(f"  时间跳跃检测: '{word_text}' (时间间隔: {word_info.get('start', 0) - word_timestamps[current_index-2].get('end', 0):.2f}s)")
            elif self._is_chinese_word_match(word_text, text_chars, char_index):
                matched_words.append(word_info)
                char_index += len(word_text)
                current_index += 1
                self.logger.debug(f"  匹配成功: '{word_text}'")
            else:
                # 尝试部分匹配
                if self._is_partial_chinese_match(word_text, text_chars, char_index):
                    matched_words.append(word_info)
                    char_index += 1
                    current_index += 1
                    self.logger.debug(f"  部分匹配: '{word_text}'")
                else:
                    # 跳过不匹配的单词
                    current_index += 1
                    self.logger.debug(f"  跳过不匹配: '{word_text}'")
            
            # 防止无限循环
            if len(matched_words) > max_chars * 3:
                self.logger.warning(f"匹配单词数过多，可能存在问题: {len(matched_words)}")
                break
        
        self.logger.debug(f"修复版本中文匹配完成: {len(matched_words)}个单词，char_index: {char_index}")
        return matched_words
    
    def _match_mixed_segment_fixed(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """修复版本：处理中英文混合文本的匹配算法，确保匹配所有相关的Whisper分段"""
        matched_words = []
        current_index = start_index
        
        # 将文本按中英文分割
        text_parts = self._split_mixed_text(segment_text)
        
        for part in text_parts:
            if not part.strip():
                continue
            
            # 检测每个部分的语言类型
            part_language = self._detect_text_language(part)
            
            if part_language == "chinese":
                # 使用修复版本的中文匹配算法
                part_matched = self._match_chinese_segment_fixed(part, word_timestamps, current_index)
            elif part_language == "english":
                # 使用修复版本的英文匹配算法
                part_matched = self._match_english_segment_fixed(part, word_timestamps, current_index)
            else:
                # 混合部分，使用更宽松的匹配
                part_matched = self._match_flexible_segment(part, word_timestamps, current_index)
            
            if part_matched:
                matched_words.extend(part_matched)
                current_index += len(part_matched)
            else:
                # 如果匹配失败，尝试跳过一些单词
                current_index += 1
                if current_index >= len(word_timestamps):
                    break
        
        return matched_words
    
    def _split_mixed_text(self, text: str) -> List[str]:
        """将中英文混合文本分割成纯中文和纯英文部分"""
        parts = []
        current_part = ""
        current_language = None
        
        for char in text:
            if re.match(r'[\u4e00-\u9fff]', char):
                char_language = "chinese"
            elif re.match(r'[a-zA-Z]', char):
                char_language = "english"
            else:
                char_language = "other"
            
            if current_language is None:
                current_language = char_language
                current_part = char
            elif char_language == current_language or char_language == "other":
                current_part += char
            else:
                # 语言类型改变，保存当前部分
                if current_part.strip():
                    parts.append(current_part.strip())
                current_part = char
                current_language = char_language
        
        # 添加最后一部分
        if current_part.strip():
            parts.append(current_part.strip())
        
        return parts
    
    def _match_flexible_segment(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """灵活的匹配算法，用于处理复杂的混合文本"""
        matched_words = []
        current_index = start_index
        
        # 清理文本
        clean_text = re.sub(r'[^\w\u4e00-\u9fff]', '', segment_text)
        
        if not clean_text:
            return matched_words
        
        # 使用更宽松的匹配策略
        text_chars = list(clean_text)
        char_index = 0
        
        while current_index < len(word_timestamps) and char_index < len(text_chars):
            word_info = word_timestamps[current_index]
            word_text = word_info.get('word', '').strip()
            
            # 清理单词
            clean_word = re.sub(r'[^\w\u4e00-\u9fff]', '', word_text)
            
            if not clean_word:
                current_index += 1
                continue
            
            # 尝试匹配
            if self._is_flexible_match(clean_word, text_chars, char_index):
                matched_words.append(word_info)
                char_index += len(clean_word)
            else:
                # 如果不匹配，检查是否是标点符号
                if word_text in self.punctuation_marks or word_text.isspace():
                    matched_words.append(word_info)
                else:
                    # 尝试部分匹配
                    if self._is_partial_match(clean_word, text_chars, char_index):
                        matched_words.append(word_info)
                        char_index += 1
                    else:
                        break
            
            current_index += 1
            
            # 防止无限循环
            if len(matched_words) > len(text_chars) * 3:
                break
        
        return matched_words
    
    def _is_flexible_match(self, word: str, text_chars: List[str], start_index: int) -> bool:
        """检查单词是否与文本字符灵活匹配"""
        if start_index + len(word) > len(text_chars):
            return False
        
        for i, char in enumerate(word):
            if start_index + i >= len(text_chars):
                return False
            if char != text_chars[start_index + i]:
                return False
        
        return True
    
    def _is_partial_match(self, word: str, text_chars: List[str], start_index: int) -> bool:
        """检查单词是否与文本字符部分匹配"""
        if start_index >= len(text_chars):
            return False
        
        # 检查第一个字符是否匹配
        return word[0] == text_chars[start_index] if word else False
    
    def _match_chinese_segment(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """优化的中文分段匹配算法，提高性能"""
        matched_words = []
        current_index = start_index
        
        # 清理分段文本，移除标点符号进行匹配
        clean_segment = re.sub(r'[。！？\.\!\?\s]', '', segment_text.strip())
        
        if not clean_segment:
            return matched_words
        
        # 使用更高效的匹配策略
        text_chars = list(clean_segment)
        char_index = 0
        max_chars = len(text_chars)
        
        # 预编译正则表达式，提高性能
        punctuation_pattern = re.compile(r'[。！？\.\!\?\s]')
        
        while current_index < len(word_timestamps) and char_index < max_chars:
            word_info = word_timestamps[current_index]
            word_text = word_info.get('word', '').strip()
            
            # 使用预编译的正则表达式
            clean_word = punctuation_pattern.sub('', word_text)
            
            if not clean_word:
                current_index += 1
                continue
            
            # 使用更高效的匹配算法
            match_result = self._fast_chinese_match(clean_word, text_chars, char_index)
            
            if match_result['matched']:
                matched_words.append(word_info)
                char_index = match_result['new_index']
            else:
                # 如果没有匹配，检查是否是标点符号或空格
                if word_text in self.punctuation_marks or word_text.isspace():
                    matched_words.append(word_info)
                else:
                    # 尝试部分匹配（至少匹配一个字符）
                    if self._is_partial_chinese_match(clean_word, text_chars, char_index):
                        matched_words.append(word_info)
                        char_index += 1
                    else:
                        # 如果完全不匹配，停止匹配
                        break
            
            current_index += 1
            
            # 防止无限循环
            if len(matched_words) > max_chars * 3:
                break
        
        return matched_words
    
    def _fast_chinese_match(self, word: str, text_chars: List[str], start_index: int) -> Dict[str, Any]:
        """快速中文匹配算法"""
        word_chars = list(word)
        char_index = start_index
        matched_chars = 0
        
        for word_char in word_chars:
            if char_index < len(text_chars) and word_char == text_chars[char_index]:
                char_index += 1
                matched_chars += 1
            else:
                break
        
        return {
            'matched': matched_chars > 0,
            'new_index': char_index,
            'matched_chars': matched_chars
        }
    
    def _is_partial_chinese_match(self, word: str, text_chars: List[str], start_index: int) -> bool:
        """检查中文单词是否与文本字符部分匹配"""
        if start_index >= len(text_chars):
            return False
        
        # 检查第一个字符是否匹配
        return word[0] == text_chars[start_index] if word else False
    
    def _match_english_segment(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """优化的英文分段匹配算法，提高性能"""
        matched_words = []
        current_index = start_index
        
        # 清理分段文本
        clean_segment = segment_text.strip()
        
        if not clean_segment:
            return matched_words
        
        # 预编译正则表达式，提高性能
        word_pattern = re.compile(r'\b\w+\b')
        clean_word_pattern = re.compile(r'[^\w]')
        
        # 将分段文本按单词分割，保持原始大小写
        segment_words = word_pattern.findall(clean_segment)
        word_index = 0
        max_words = len(segment_words)
        
        # 添加调试日志
        self.logger.debug(f"开始匹配英文分段: '{clean_segment[:50]}...'")
        self.logger.debug(f"分段单词数: {max_words}, 起始索引: {start_index}")
        
        while current_index < len(word_timestamps) and word_index < max_words:
            word_info = word_timestamps[current_index]
            word_text = word_info.get('word', '').strip()
            
            # 使用预编译的正则表达式
            clean_word = clean_word_pattern.sub('', word_text)
            
            if not clean_word:
                current_index += 1
                continue
            
            # 使用快速匹配算法
            match_result = self._fast_english_match(clean_word, segment_words[word_index])
            
            if match_result['matched']:
                matched_words.append(word_info)
                word_index += 1
                self.logger.debug(f"  匹配成功: '{clean_word}' -> '{segment_words[word_index-1]}'")
            elif word_text in self.punctuation_marks or word_text.isspace():
                # 标点符号和空格也加入匹配
                matched_words.append(word_info)
                self.logger.debug(f"  标点符号匹配: '{word_text}'")
            else:
                # 如果不匹配，检查是否是变体（如复数、时态等）
                if self._is_word_variant(clean_word, segment_words[word_index]):
                    matched_words.append(word_info)
                    word_index += 1
                    self.logger.debug(f"  变体匹配: '{clean_word}' -> '{segment_words[word_index-1]}'")
                else:
                    # 尝试部分匹配
                    if self._is_partial_english_match(clean_word, segment_words[word_index]):
                        matched_words.append(word_info)
                        word_index += 1
                        self.logger.debug(f"  部分匹配: '{clean_word}' -> '{segment_words[word_index-1]}'")
                    else:
                        # 如果完全不匹配，跳过当前word_timestamp，继续尝试
                        # 这样可以处理转录中可能的小错误或漏词
                        self.logger.debug(f"  跳过不匹配: '{clean_word}' (期望: '{segment_words[word_index]}')")
                        current_index += 1
                        # 如果跳过了太多单词，增加word_index以避免无限循环
                        if current_index - start_index > max_words * 2:
                            word_index += 1
                        continue  # 跳过当前循环，不增加word_index
            
            current_index += 1
            
            # 防止无限循环
            if len(matched_words) > max_words * 3:
                self.logger.warning(f"匹配单词数过多，可能存在问题: {len(matched_words)}")
                break
        
        self.logger.debug(f"匹配完成: {len(matched_words)}个单词，word_index: {word_index}")
        return matched_words
    
    def _match_english_segment_fixed(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """修复版本：英文分段匹配算法，确保匹配所有相关的Whisper分段"""
        matched_words = []
        current_index = start_index
        
        # 清理分段文本
        clean_segment = segment_text.strip()
        if not clean_segment:
            return matched_words
        
        # 预编译正则表达式，提高性能
        word_pattern = re.compile(r'\b\w+\b')
        clean_word_pattern = re.compile(r'[^\w]')
        
        # 将分段文本按单词分割，使用更智能的分割
        segment_words = self._smart_word_split(clean_segment)
        word_index = 0
        max_words = len(segment_words)
        
        self.logger.debug(f"修复版本：开始匹配英文分段: '{clean_segment[:50]}...'")
        self.logger.debug(f"分段单词数: {max_words}, 起始索引: {start_index}")
        
        while current_index < len(word_timestamps) and word_index < max_words:
            word_info = word_timestamps[current_index]
            word_text = word_info.get('word', '').strip()
            clean_word = clean_word_pattern.sub('', word_text)
            
            if not clean_word:
                current_index += 1
                continue
            
            # 检查是否匹配当前期望的单词
            expected_word = segment_words[word_index].lower()
            actual_word = clean_word.lower()
            
            if actual_word == expected_word or self._is_word_variant(actual_word, expected_word):
                matched_words.append(word_info)
                word_index += 1
                current_index += 1
                self.logger.debug(f"  匹配成功: '{clean_word}' -> '{segment_words[word_index-1]}'")
            elif word_text in self.punctuation_marks or word_text.isspace():
                # 标点符号和空格也加入匹配
                matched_words.append(word_info)
                current_index += 1
                self.logger.debug(f"  标点符号匹配: '{word_text}'")
            else:
                # 检查是否是时间跳跃（新的Whisper分段）
                if self._is_time_jump(word_timestamps, current_index):
                    # 发现时间跳跃，说明进入了新的Whisper分段
                    # 继续匹配，但记录时间跳跃
                    matched_words.append(word_info)
                    current_index += 1
                    self.logger.debug(f"  时间跳跃检测: '{clean_word}' (时间间隔: {word_info.get('start', 0) - word_timestamps[current_index-2].get('end', 0):.2f}s)")
                else:
                    # 尝试部分匹配
                    if self._is_partial_match(clean_word, expected_word):
                        matched_words.append(word_info)
                        word_index += 1
                        current_index += 1
                        self.logger.debug(f"  部分匹配: '{clean_word}' -> '{segment_words[word_index-1]}'")
                    else:
                        # 跳过不匹配的单词
                        current_index += 1
                        self.logger.debug(f"  跳过不匹配: '{clean_word}' (期望: '{expected_word}')")
            
            # 防止无限循环
            if len(matched_words) > max_words * 3:
                self.logger.warning(f"匹配单词数过多，可能存在问题: {len(matched_words)}")
                break
        
        self.logger.debug(f"修复版本匹配完成: {len(matched_words)}个单词，word_index: {word_index}")
        return matched_words
    
    def _fast_english_match(self, word1: str, word2: str) -> Dict[str, Any]:
        """快速英文匹配算法"""
        if not word1 or not word2:
            return {'matched': False}
        
        # 大小写不敏感匹配
        if word1.lower() == word2.lower():
            return {'matched': True}
        
        return {'matched': False}
    
    def _is_word_match(self, word1: str, word2: str) -> bool:
        """检查两个单词是否匹配（大小写不敏感）"""
        if not word1 or not word2:
            return False
        
        return word1.lower() == word2.lower()
    
    def _is_partial_english_match(self, word1: str, word2: str) -> bool:
        """检查英文单词是否部分匹配"""
        if not word1 or not word2:
            return False
        
        # 检查词根是否相同
        if len(word1) > 2 and len(word2) > 2:
            return word1.lower()[:3] == word2.lower()[:3]
        
        return False
    
    def _is_word_variant(self, word1: str, word2: str) -> bool:
        """检查两个单词是否是变体关系，支持更多变体类型"""
        if not word1 or not word2:
            return False
        
        # 转换为小写进行比较
        word1_lower = word1.lower()
        word2_lower = word2.lower()
        
        # 完全匹配
        if word1_lower == word2_lower:
            return True
        
        # 处理缩写词的特殊情况
        if self._is_abbreviation_variant(word1_lower, word2_lower):
            return True
        
        # 检查词根是否相同
        if len(word1_lower) > 3 and len(word2_lower) > 3:
            if word1_lower[:3] == word2_lower[:3]:
                return True
        
        # 检查常见的变体关系
        if self._is_common_variant(word1_lower, word2_lower):
            return True
        
        # 检查编辑距离（简单的相似度检查）
        if self._is_similar_word(word1_lower, word2_lower):
            return True
        
        return False
    
    def _is_abbreviation_variant(self, word1: str, word2: str) -> bool:
        """检查缩写词的变体关系"""
        # 常见的缩写词映射
        abbreviation_map = {
            "im": "i'm",
            "im": "i'm",
            "youre": "you're",
            "youre": "you're",
            "were": "we're",
            "were": "we're",
            "theyre": "they're",
            "theyre": "they're",
            "dont": "don't",
            "dont": "don't",
            "wont": "won't",
            "wont": "won't",
            "cant": "can't",
            "cant": "can't",
            "isnt": "isn't",
            "isnt": "isn't",
            "arent": "aren't",
            "arent": "aren't",
            "hasnt": "hasn't",
            "hasnt": "hasn't",
            "havent": "haven't",
            "havent": "haven't",
            "hadnt": "hadn't",
            "hadnt": "hadn't",
            "wouldnt": "wouldn't",
            "wouldnt": "wouldn't",
            "shouldnt": "shouldn't",
            "shouldnt": "shouldn't",
            "couldnt": "couldn't",
            "couldnt": "couldn't",
            "didnt": "didn't",
            "didnt": "didn't",
            "doesnt": "doesn't",
            "doesnt": "doesn't",
            "thats": "that's",
            "thats": "that's",
            "theres": "there's",
            "theres": "there's",
            "its": "it's",
            "its": "it's",
        }
        
        # 检查直接映射
        if word1 in abbreviation_map and abbreviation_map[word1] == word2:
            return True
        if word2 in abbreviation_map and abbreviation_map[word2] == word1:
            return True
        
        return False
    
    def _is_common_variant(self, word1: str, word2: str) -> bool:
        """检查常见的单词变体关系"""
        # 常见的变体模式
        variants = [
            # 复数形式
            (word1 + 's', word2),
            (word1, word2 + 's'),
            (word1 + 'es', word2),
            (word1, word2 + 'es'),
            # 过去式
            (word1 + 'ed', word2),
            (word1, word2 + 'ed'),
            # 进行时
            (word1 + 'ing', word2),
            (word1, word2 + 'ing'),
            # 第三人称单数
            (word1 + 's', word2),
            (word1, word2 + 's'),
        ]
        
        for variant1, variant2 in variants:
            if variant1 == word2 or variant2 == word1:
                return True
        
        return False
    
    def _is_similar_word(self, word1: str, word2: str) -> bool:
        """检查两个单词是否相似（基于编辑距离）"""
        if abs(len(word1) - len(word2)) > 2:
            return False
        
        # 简单的编辑距离检查
        distance = self._calculate_edit_distance(word1, word2)
        max_length = max(len(word1), len(word2))
        
        # 如果编辑距离小于最大长度的30%，认为是相似的
        return distance < max_length * 0.3
    
    def _is_chinese_word_match(self, word_text: str, text_chars: List[str], char_index: int) -> bool:
        """检查中文单词是否匹配"""
        if not word_text or char_index >= len(text_chars):
            return False
        
        # 检查单词的第一个字符是否匹配
        return word_text[0] == text_chars[char_index] if word_text else False
    
    def _is_time_jump(self, word_timestamps: List[Dict[str, Any]], current_index: int) -> bool:
        """检测是否是时间跳跃（新的Whisper分段）"""
        if current_index <= 0 or current_index >= len(word_timestamps):
            return False
        
        current_word = word_timestamps[current_index]
        prev_word = word_timestamps[current_index - 1]
        
        # 如果时间间隔超过15秒，可能是新的分段（大幅放宽阈值）
        time_gap = current_word.get('start', 0) - prev_word.get('end', 0)
        return time_gap > 15.0
    
    def _smart_word_split(self, text: str) -> List[str]:
        """智能单词分割，正确处理缩写和标点符号"""
        import re
        
        # 处理常见的缩写
        text = re.sub(r"(\w+)'s\b", r"\1's", text)  # 保持 's 不分割
        text = re.sub(r"(\w+)'re\b", r"\1're", text)  # 保持 're 不分割
        text = re.sub(r"(\w+)'ve\b", r"\1've", text)  # 保持 've 不分割
        text = re.sub(r"(\w+)'ll\b", r"\1'll", text)  # 保持 'll 不分割
        text = re.sub(r"(\w+)'t\b", r"\1't", text)  # 保持 't 不分割
        text = re.sub(r"(\w+)'d\b", r"\1'd", text)  # 保持 'd 不分割
        
        # 按单词边界分割，但保持缩写完整
        words = re.findall(r"\b\w+(?:'\w+)?\b", text)
        
        return words
    
    def _is_partial_match(self, word1: str, word2: str) -> bool:
        """检查两个单词是否部分匹配"""
        if not word1 or not word2:
            return False
        
        # 检查词根是否相同
        if len(word1) > 2 and len(word2) > 2:
            return word1.lower()[:3] == word2.lower()[:3]
        
        return False
    
    def _calculate_edit_distance(self, word1: str, word2: str) -> int:
        """计算两个单词的编辑距离"""
        m, n = len(word1), len(word2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if word1[i-1] == word2[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
        
        return dp[m][n]
    
    def _is_chinese_text(self, text: str) -> bool:
        """判断文本是否包含中文字符"""
        import re
        chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        return bool(chinese_pattern.search(text))
    
    def _control_segment_length(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """重新设计的长度控制逻辑，确保覆盖整个音频时长"""
        if not segments:
            return []
        
        # 第一步：获取音频总时长
        audio_total_duration = self._get_audio_total_duration(segments)
        self.logger.info(f"音频总时长: {audio_total_duration:.2f}秒")
        
        # 第二步：智能合并短分段
        final_segments = self._merge_short_segments(segments)
        
        # 第三步：检查覆盖完整性
        final_segments = self._ensure_complete_coverage(final_segments, audio_total_duration)
        
        # 第四步：最终质量检查
        final_segments = self._final_quality_check(final_segments)
        
        return final_segments
    
    def _get_audio_total_duration(self, segments: List[Dict[str, Any]]) -> float:
        """获取音频总时长"""
        if not segments:
            return 0.0
        
        # 从单词时间戳中获取最大时间
        max_time = 0.0
        for segment in segments:
            words = segment.get('words', [])
            if words:
                segment_max = max(word.get('end', 0) for word in words)
                max_time = max(max_time, segment_max)
        
        # 如果没有单词时间戳，使用分段的最大结束时间
        if max_time == 0.0:
            max_time = max(segment.get('end', 0) for segment in segments)
        
        return max_time
    
    def _merge_short_segments(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """智能合并短分段"""
        if not segments:
            return []
        
        final_segments = []
        i = 0
        
        while i < len(segments):
            current_segment = segments[i]
            current_duration = current_segment['end'] - current_segment['start']
            current_text = current_segment['text']
            
            # 如果分段太短，尝试与后续分段合并
            if current_duration < self.min_segment_duration and i + 1 < len(segments):
                merged_text = current_text
                merged_end = current_segment['end']
                merged_words = current_segment.get('words', [])
                j = i + 1
                
                # 继续合并后续的短分段
                while j < len(segments):
                    next_segment = segments[j]
                    next_duration = next_segment['end'] - next_segment['start']
                    next_text = next_segment['text']
                    
                    # 检查合并后的总时长
                    total_duration = next_segment['end'] - current_segment['start']
                    
                    # 如果合并后不超过最大时长，继续合并
                    if total_duration <= self.max_segment_duration:
                        # 使用智能连接方式
                        merged_text = self._smart_text_connection(merged_text, next_text)
                        merged_end = next_segment['end']
                        merged_words.extend(next_segment.get('words', []))
                        j += 1
                    else:
                        break
                
                # 创建合并后的分段
                merged_segment = {
                    'start': current_segment['start'],
                    'end': merged_end,
                    'text': merged_text,
                    'words': merged_words
                }
                # 保留speaker_id（如果存在）
                if 'speaker_id' in current_segment:
                    merged_segment['speaker_id'] = current_segment['speaker_id']
                final_segments.append(merged_segment)
                self.logger.info(f"合并分段: {current_segment['start']:.2f}s-{merged_end:.2f}s (合并了{j-i}个分段)")
                i = j  # 跳过已合并的分段
            else:
                # 分段长度合适，直接添加
                final_segments.append(current_segment)
                i += 1
        
        return final_segments
    
    def _ensure_complete_coverage(self, segments: List[Dict[str, Any]], audio_total_duration: float) -> List[Dict[str, Any]]:
        """确保覆盖整个音频时长"""
        if not segments or audio_total_duration <= 0:
            return segments
        
        last_segment = segments[-1]
        last_end_time = last_segment['end']
        
        # 检查是否覆盖到音频末尾
        if last_end_time < audio_total_duration - 0.5:  # 允许0.5秒误差
            self.logger.warning(f"⚠️ 分段不完整: 最后分段到{last_end_time:.2f}s，但音频总时长{audio_total_duration:.2f}s")
            self.logger.warning(f"⚠️ 缺失{audio_total_duration - last_end_time:.2f}秒的音频内容")
            
            # 创建剩余部分的分段
            remaining_segment = {
                'start': last_end_time,
                'end': audio_total_duration,
                'text': f"[剩余音频内容 {last_end_time:.2f}s-{audio_total_duration:.2f}s]",
                'words': []
            }
            segments.append(remaining_segment)
            self.logger.info(f"添加剩余分段: {last_end_time:.2f}s-{audio_total_duration:.2f}s")
        
        return segments
    
    def _final_quality_check(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """最终质量检查"""
        if not segments:
            return segments
        
        # 检查每个分段的时长是否合理
        for i, segment in enumerate(segments):
            duration = segment['end'] - segment['start']
            if duration > self.max_segment_duration * 1.5:  # 允许50%的误差
                self.logger.warning(f"⚠️ 分段{i}过长: {duration:.2f}秒 (超过{self.max_segment_duration}秒)")
            
            if duration < 0.5:  # 分段太短
                self.logger.warning(f"⚠️ 分段{i}过短: {duration:.2f}秒")
        
        return segments
    
    def _smart_text_connection(self, text1: str, text2: str) -> str:
        """智能文本连接，根据语言类型选择连接方式"""
        if not text1 or not text2:
            return text1 + text2
        
        # 检测两个文本的语言类型
        lang1 = self._detect_text_language(text1)
        lang2 = self._detect_text_language(text2)
        
        # 如果都是中文，直接连接
        if lang1 == "chinese" and lang2 == "chinese":
            return text1 + text2
        
        # 如果都是英文，加空格连接
        elif lang1 == "english" and lang2 == "english":
            return text1 + " " + text2
        
        # 如果一个是中文，一个是英文，根据位置决定
        elif lang1 == "chinese" and lang2 == "english":
            # 中文在前，英文在后，加空格
            return text1 + " " + text2
        elif lang1 == "english" and lang2 == "chinese":
            # 英文在前，中文在后，加空格
            return text1 + " " + text2
        
        # 混合文本，使用更智能的连接方式
        else:
            return self._connect_mixed_text(text1, text2)
    
    def _connect_mixed_text(self, text1: str, text2: str) -> str:
        """连接混合文本，使用更智能的方式"""
        # 检查text1的结尾和text2的开头
        text1_end = text1[-1] if text1 else ''
        text2_start = text2[0] if text2 else ''
        
        # 如果text1以标点符号结尾，直接连接
        if text1_end in self.punctuation_marks:
            return text1 + text2
        
        # 如果text2以标点符号开头，直接连接
        if text2_start in self.punctuation_marks:
            return text1 + text2
        
        # 如果text1以中文字符结尾，text2以英文字符开头，加空格
        if (re.match(r'[\u4e00-\u9fff]', text1_end) and 
            re.match(r'[a-zA-Z]', text2_start)):
            return text1 + " " + text2
        
        # 如果text1以英文字符结尾，text2以中文字符开头，加空格
        if (re.match(r'[a-zA-Z]', text1_end) and 
            re.match(r'[\u4e00-\u9fff]', text2_start)):
            return text1 + " " + text2
        
        # 其他情况，直接连接
        return text1 + text2
    
    def save_optimization_result(self, optimized_segments: List[Dict[str, Any]], 
                               output_path: str) -> None:
        """保存优化结果"""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            result = {
                "optimized_segments": optimized_segments,
                "total_segments": len(optimized_segments),
                "optimization_info": {
                    "min_segment_duration": self.min_segment_duration,
                    "max_segment_duration": self.max_segment_duration,
                    "method": "punctuation_based_optimization",
                    "punctuation_marks": self.punctuation_marks,
                    "min_segment_length": self.min_segment_length,
                    "max_segment_length": self.max_segment_length
                }
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"✅ 优化结果已保存: {output_path}")
            
        except Exception as e:
            self.logger.error(f"保存优化结果失败: {e}")
            raise
    
    def _find_matching_words_within_segments(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """修复版本：在Whisper原始分段内查找匹配的单词，避免跨分段匹配"""
        if start_index >= len(word_timestamps):
            return []
        
        # 处理边界情况
        if not segment_text or not segment_text.strip():
            return []
        
        # 清理文本，移除多余空格
        clean_text = ' '.join(segment_text.split())
        
        # 使用更智能的语言检测
        language_type = self._detect_text_language(clean_text)
        
        if language_type == "chinese":
            return self._match_chinese_segment_within_boundaries(clean_text, word_timestamps, start_index)
        elif language_type == "english":
            return self._match_english_segment_within_boundaries(clean_text, word_timestamps, start_index)
        else:
            # 中英文混合文本，使用混合匹配策略
            return self._match_mixed_segment_within_boundaries(clean_text, word_timestamps, start_index)
    
    def _match_english_segment_within_boundaries(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """修复版本：在Whisper原始分段内匹配英文分段，避免跨分段匹配"""
        matched_words = []
        current_index = start_index
        
        # 清理分段文本
        clean_segment = segment_text.strip()
        if not clean_segment:
            return matched_words
        
        # 将分段文本按单词分割
        segment_words = self._smart_word_split(clean_segment)
        word_index = 0
        max_words = len(segment_words)
        
        self.logger.debug(f"修复版本：开始匹配英文分段: '{clean_segment[:50]}...'")
        self.logger.debug(f"分段单词数: {max_words}, 起始索引: {start_index}")
        
        while current_index < len(word_timestamps) and word_index < max_words:
            word_info = word_timestamps[current_index]
            word_text = word_info.get('word', '').strip()
            
            # 检查是否遇到时间跳跃（新的Whisper分段）
            if self._is_time_jump(word_timestamps, current_index):
                self.logger.debug(f"检测到时间跳跃，停止匹配以避免跨分段")
                break
            
            # 清理单词文本
            clean_word = re.sub(r'[^\w]', '', word_text)
            
            if not clean_word:
                current_index += 1
                continue
            
            # 检查是否匹配当前期望的单词
            expected_word = segment_words[word_index].lower()
            actual_word = clean_word.lower()
            
            if actual_word == expected_word or self._is_word_variant(actual_word, expected_word):
                matched_words.append(word_info)
                word_index += 1
                current_index += 1
                self.logger.debug(f"  匹配成功: '{clean_word}' -> '{segment_words[word_index-1]}'")
            elif word_text in self.punctuation_marks or word_text.isspace():
                # 标点符号和空格也加入匹配
                matched_words.append(word_info)
                current_index += 1
                self.logger.debug(f"  标点符号匹配: '{word_text}'")
            else:
                # 不匹配，尝试跳过一些单词
                current_index += 1
                if current_index >= len(word_timestamps):
                    break
        
        self.logger.debug(f"英文分段匹配完成: {len(matched_words)} 个单词")
        return matched_words
    
    def _match_chinese_segment_within_boundaries(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """修复版本：在Whisper原始分段内匹配中文分段，避免跨分段匹配"""
        matched_words = []
        current_index = start_index
        
        # 清理分段文本
        clean_segment = segment_text.strip()
        if not clean_segment:
            return matched_words
        
        # 将分段文本按字符分割
        segment_chars = list(clean_segment)
        char_index = 0
        max_chars = len(segment_chars)
        
        self.logger.debug(f"修复版本：开始匹配中文分段: '{clean_segment[:50]}...'")
        self.logger.debug(f"分段字符数: {max_chars}, 起始索引: {start_index}")
        
        while current_index < len(word_timestamps) and char_index < max_chars:
            word_info = word_timestamps[current_index]
            word_text = word_info.get('word', '').strip()
            
            # 检查是否遇到时间跳跃（新的Whisper分段）
            if self._is_time_jump(word_timestamps, current_index):
                self.logger.debug(f"检测到时间跳跃，停止匹配以避免跨分段")
                break
            
            # 清理单词文本
            clean_word = re.sub(r'[^\w\u4e00-\u9fff]', '', word_text)
            
            if not clean_word:
                current_index += 1
                continue
            
            # 检查是否匹配当前期望的字符
            expected_char = segment_chars[char_index]
            actual_char = clean_word[0] if clean_word else ''
            
            if actual_char == expected_char:
                matched_words.append(word_info)
                char_index += 1
                current_index += 1
                self.logger.debug(f"  匹配成功: '{actual_char}' -> '{expected_char}'")
            else:
                # 不匹配，尝试跳过一些单词
                current_index += 1
                if current_index >= len(word_timestamps):
                    break
        
        self.logger.debug(f"中文分段匹配完成: {len(matched_words)} 个单词")
        return matched_words
    
    def _match_mixed_segment_within_boundaries(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """修复版本：在Whisper原始分段内匹配中英文混合分段，避免跨分段匹配"""
        matched_words = []
        current_index = start_index
        
        # 将文本按中英文分割
        text_parts = self._split_mixed_text(segment_text)
        
        for part in text_parts:
            if not part.strip():
                continue
            
            # 检测每个部分的语言类型
            part_language = self._detect_text_language(part)
            
            if part_language == "chinese":
                # 使用中文匹配算法
                part_matched = self._match_chinese_segment_within_boundaries(part, word_timestamps, current_index)
            elif part_language == "english":
                # 使用英文匹配算法
                part_matched = self._match_english_segment_within_boundaries(part, word_timestamps, current_index)
            else:
                # 混合部分，使用更宽松的匹配
                part_matched = self._match_flexible_segment_within_boundaries(part, word_timestamps, current_index)
            
            if part_matched:
                matched_words.extend(part_matched)
                current_index += len(part_matched)
            else:
                # 如果匹配失败，尝试跳过一些单词
                current_index += 1
                if current_index >= len(word_timestamps):
                    break
        
        return matched_words
    
    def _match_flexible_segment_within_boundaries(self, segment_text: str, word_timestamps: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
        """修复版本：在Whisper原始分段内进行灵活的匹配，避免跨分段匹配"""
        matched_words = []
        current_index = start_index
        
        # 清理分段文本
        clean_segment = segment_text.strip()
        if not clean_segment:
            return matched_words
        
        # 使用更宽松的匹配策略
        segment_words = self._smart_word_split(clean_segment)
        word_index = 0
        max_words = len(segment_words)
        
        while current_index < len(word_timestamps) and word_index < max_words:
            word_info = word_timestamps[current_index]
            word_text = word_info.get('word', '').strip()
            
            # 检查是否遇到时间跳跃（新的Whisper分段）
            if self._is_time_jump(word_timestamps, current_index):
                self.logger.debug(f"检测到时间跳跃，停止匹配以避免跨分段")
                break
            
            # 清理单词文本
            clean_word = re.sub(r'[^\w\u4e00-\u9fff]', '', word_text)
            
            if not clean_word:
                current_index += 1
                continue
            
            # 使用更宽松的匹配
            expected_word = segment_words[word_index].lower()
            actual_word = clean_word.lower()
            
            if (actual_word == expected_word or 
                self._is_word_variant(actual_word, expected_word) or
                self._is_flexible_match(actual_word, expected_word)):
                matched_words.append(word_info)
                word_index += 1
                current_index += 1
            else:
                # 不匹配，尝试跳过一些单词
                current_index += 1
                if current_index >= len(word_timestamps):
                    break
        
        return matched_words
    
    def _is_flexible_match(self, actual_word: str, expected_word: str) -> bool:
        """检查是否是灵活的匹配（用于混合文本）"""
        if not actual_word or not expected_word:
            return False
        
        # 检查是否是部分匹配
        if actual_word in expected_word or expected_word in actual_word:
            return True
        
        # 检查是否是变体
        if self._is_word_variant(actual_word, expected_word):
            return True
        
        return False
