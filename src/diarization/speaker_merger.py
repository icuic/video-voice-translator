"""
说话人短片段相似度合并模块
基于声音特征相似度，将过短的片段合并到最相似的说话人
"""

import os
import logging
import numpy as np
import librosa
from typing import List, Dict, Any, Tuple, Optional
from resemblyzer import VoiceEncoder, preprocess_wav
from resemblyzer.hparams import sampling_rate


class SpeakerMerger:
    """基于声音相似度的说话人短片段合并器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化说话人合并器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 相似度合并配置
        merge_cfg = config.get("speaker_tracks", {}).get("similarity_merge", {})
        self.enabled = merge_cfg.get("enabled", True)
        self.short_segment_threshold = merge_cfg.get("short_segment_threshold", 2.0)  # 秒
        self.similarity_threshold = merge_cfg.get("similarity_threshold", 0.7)  # 0-1
        
        # 初始化语音编码器
        self.encoder = None
        if self.enabled:
            try:
                self.logger.info("初始化语音编码器用于相似度计算")
                self.encoder = VoiceEncoder()
                self.logger.info("语音编码器初始化成功")
            except Exception as e:
                self.logger.warning(f"语音编码器初始化失败，相似度合并将被禁用: {e}")
                self.enabled = False
    
    def merge_short_segments_by_similarity(
        self, 
        segments: List[Dict[str, Any]], 
        audio_path: str
    ) -> List[Dict[str, Any]]:
        """
        基于声音相似度合并短片段
        
        Args:
            segments: 说话人片段列表，格式 [{start, end, speaker_id, confidence}]
            audio_path: 音频文件路径
            
        Returns:
            合并后的说话人片段列表
        """
        if not self.enabled or not self.encoder:
            self.logger.info("相似度合并未启用，跳过")
            return segments
        
        if not segments or len(segments) < 2:
            return segments
        
        # 加载音频
        try:
            audio, sr = librosa.load(audio_path, sr=sampling_rate)
        except Exception as e:
            self.logger.warning(f"无法加载音频文件，跳过相似度合并: {e}")
            return segments
        
        # 按说话人分组片段
        speaker_segments: Dict[str, List[Dict[str, Any]]] = {}
        for seg in segments:
            spk_id = seg.get("speaker_id", "speaker_0")
            if spk_id not in speaker_segments:
                speaker_segments[spk_id] = []
            speaker_segments[spk_id].append(seg)
        
        # 识别短片段和长片段说话人
        short_segments: List[Dict[str, Any]] = []
        long_speakers: Dict[str, List[Dict[str, Any]]] = {}
        
        for spk_id, segs in speaker_segments.items():
            total_duration = sum(seg.get("end", 0.0) - seg.get("start", 0.0) for seg in segs)
            if total_duration < self.short_segment_threshold:
                # 短片段说话人
                short_segments.extend(segs)
            else:
                # 长片段说话人
                long_speakers[spk_id] = segs
        
        if not short_segments or not long_speakers:
            self.logger.info(f"未检测到需要合并的短片段（短片段: {len(short_segments)}, 长说话人: {len(long_speakers)}）")
            return segments
        
        self.logger.info(f"检测到 {len(short_segments)} 个短片段，{len(long_speakers)} 个长说话人")
        
        # 为每个长说话人生成代表性嵌入向量
        speaker_embeddings: Dict[str, np.ndarray] = {}
        for spk_id, segs in long_speakers.items():
            embedding = self._extract_speaker_embedding(segs, audio, sr)
            if embedding is not None:
                speaker_embeddings[spk_id] = embedding
        
        if not speaker_embeddings:
            self.logger.warning("无法提取说话人嵌入向量，跳过相似度合并")
            return segments
        
        # 合并短片段到最相似的说话人
        merged_segments: List[Dict[str, Any]] = []
        merged_count = 0
        
        # 先添加所有长片段说话人的片段
        for spk_id, segs in long_speakers.items():
            merged_segments.extend(segs)
        
        # 处理短片段
        for seg in short_segments:
            best_match_result = self._find_best_speaker_match(seg, speaker_embeddings, audio, sr)
            if best_match_result:
                # 合并到目标说话人
                merged_spk_id = best_match_result["speaker_id"]
                similarity = best_match_result["similarity"]
                merged_segments.append({
                    **seg,
                    "speaker_id": merged_spk_id
                })
                merged_count += 1
                self.logger.info(
                    f"短片段 {seg.get('start', 0.0):.2f}s-{seg.get('end', 0.0):.2f}s "
                    f"(原: {seg.get('speaker_id')}) 合并到 {merged_spk_id} "
                    f"(相似度: {similarity:.3f})"
                )
            else:
                # 无法找到匹配，保持原样
                merged_segments.append(seg)
                self.logger.warning(
                    f"短片段 {seg.get('start', 0.0):.2f}s-{seg.get('end', 0.0):.2f}s "
                    f"无法找到匹配的说话人，保持原样"
                )
        
        # 按时间排序
        merged_segments.sort(key=lambda x: (x.get("start", 0.0), x.get("end", 0.0)))
        
        self.logger.info(f"相似度合并完成：成功合并 {merged_count}/{len(short_segments)} 个短片段")
        return merged_segments
    
    def _extract_speaker_embedding(
        self, 
        segments: List[Dict[str, Any]], 
        audio: np.ndarray, 
        sr: int
    ) -> Optional[np.ndarray]:
        """
        为说话人生成代表性嵌入向量
        
        策略：使用最长的几个片段来生成嵌入向量，或使用所有片段的平均值
        
        Args:
            segments: 说话人的片段列表
            audio: 音频数组
            sr: 采样率
            
        Returns:
            说话人的嵌入向量，如果提取失败返回None
        """
        if not segments:
            return None
        
        # 按时长排序，使用最长的几个片段（至少取前3个或全部）
        sorted_segs = sorted(
            segments, 
            key=lambda s: s.get("end", 0.0) - s.get("start", 0.0), 
            reverse=True
        )
        num_segments = min(len(sorted_segs), max(3, len(sorted_segs) // 2))
        selected_segs = sorted_segs[:num_segments]
        
        embeddings = []
        for seg in selected_segs:
            start = int(seg.get("start", 0.0) * sr)
            end = int(seg.get("end", 0.0) * sr)
            start = max(0, min(start, len(audio)))
            end = max(start, min(end, len(audio)))
            
            if end <= start:
                continue
            
            segment_audio = audio[start:end]
            
            try:
                # 预处理音频（resemblyzer要求）
                processed = preprocess_wav(segment_audio, sr)
                # 提取嵌入向量
                embedding = self.encoder.embed_utterance(processed)
                embeddings.append(embedding)
            except Exception as e:
                self.logger.debug(f"提取嵌入向量失败: {e}")
                continue
        
        if not embeddings:
            return None
        
        # 使用平均嵌入向量作为说话人的代表性向量
        avg_embedding = np.mean(embeddings, axis=0)
        # 归一化
        norm = np.linalg.norm(avg_embedding)
        if norm > 0:
            avg_embedding = avg_embedding / norm
        
        return avg_embedding
    
    def _find_best_speaker_match(
        self, 
        segment: Dict[str, Any], 
        speaker_embeddings: Dict[str, np.ndarray], 
        audio: np.ndarray, 
        sr: int
    ) -> Optional[Dict[str, Any]]:
        """
        为短片段找到最相似的说话人
        
        Args:
            segment: 短片段
            speaker_embeddings: 说话人嵌入向量字典
            audio: 音频数组
            sr: 采样率
            
        Returns:
            包含说话人ID和相似度的字典，如果提取失败返回None
        """
        # 提取短片段的嵌入向量
        start = int(segment.get("start", 0.0) * sr)
        end = int(segment.get("end", 0.0) * sr)
        start = max(0, min(start, len(audio)))
        end = max(start, min(end, len(audio)))
        
        if end <= start:
            return None
        
        segment_audio = audio[start:end]
        
        try:
            processed = preprocess_wav(segment_audio, sr)
            segment_embedding = self.encoder.embed_utterance(processed)
            # 归一化
            norm = np.linalg.norm(segment_embedding)
            if norm > 0:
                segment_embedding = segment_embedding / norm
        except Exception as e:
            self.logger.debug(f"提取短片段嵌入向量失败: {e}")
            return None
        
        # 计算与每个说话人的相似度
        best_similarity = -1.0
        best_speaker = None
        
        for spk_id, spk_embedding in speaker_embeddings.items():
            # 余弦相似度
            similarity = np.dot(segment_embedding, spk_embedding)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_speaker = spk_id
        
        # 如果相似度超过阈值，返回最相似的说话人
        if best_similarity >= self.similarity_threshold or best_speaker is not None:
            return {
                "speaker_id": best_speaker,
                "similarity": best_similarity
            }
        
        # 无法找到匹配
        return None
