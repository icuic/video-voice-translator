"""
说话人分离器模块
使用基于音频特征的简单说话人分离
"""

import os
import logging
import numpy as np
import librosa
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from resemblyzer import VoiceEncoder, preprocess_wav
from resemblyzer.hparams import sampling_rate
from .utils import validate_file_path, create_output_dir, safe_filename


class SpeakerDiarizer:
    """说话人分离器类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化说话人分离器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 说话人分离配置
        self.diarization_config = config.get("speaker_diarization", {})
        self.model_name = self.diarization_config.get("model", "pyannote/speaker-diarization-3.1")
        self.min_speakers = self.diarization_config.get("min_speakers", 1)
        self.max_speakers = self.diarization_config.get("max_speakers", 10)
        self.device = self.diarization_config.get("device", "cpu")
        
        # 初始化语音编码器
        try:
            self.logger.info("初始化语音编码器")
            self.encoder = VoiceEncoder()
            self.logger.info("语音编码器初始化成功")
        except Exception as e:
            self.logger.error(f"语音编码器初始化失败: {e}")
            raise
    
    def diarize_audio(self, audio_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        执行说话人分离
        
        Args:
            audio_path: 音频文件路径
            output_dir: 输出目录（可选）
            
        Returns:
            分离结果字典
        """
        if not validate_file_path(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        self.logger.info(f"开始说话人分离: {audio_path}")
        
        try:
            # 执行基于特征的说话人分离
            result = self._simple_speaker_diarization(audio_path, output_dir)
            
            self.logger.info("说话人分离完成")
            return result
            
        except Exception as e:
            self.logger.error(f"说话人分离失败: {e}")
            raise
    
    def segment_by_speakers(self, audio_path: str, diarization_result: Dict[str, Any], 
                           output_dir: str) -> Dict[str, Any]:
        """
        根据说话人分离结果切分音频
        
        Args:
            audio_path: 原始音频文件路径
            diarization_result: 分离结果
            output_dir: 输出目录
            
        Returns:
            切分结果字典
        """
        self.logger.info(f"开始按说话人切分音频: {audio_path}")
        
        try:
            # 加载音频
            audio, sr = librosa.load(audio_path, sr=16000)
            
            # 创建输出目录
            create_output_dir(output_dir)
            
            # 按说话人切分
            speaker_segments = {}
            input_name = Path(audio_path).stem
            safe_name = safe_filename(input_name)
            
            for speaker_id, segments in diarization_result["speaker_segments"].items():
                speaker_audio_segments = []
                
                for segment in segments:
                    start_sample = int(segment["start"] * sr)
                    end_sample = int(segment["end"] * sr)
                    
                    # 提取音频片段
                    segment_audio = audio[start_sample:end_sample]
                    speaker_audio_segments.append(segment_audio)
                
                # 合并同一说话者的所有片段
                if speaker_audio_segments:
                    combined_audio = np.concatenate(speaker_audio_segments)
                    
                    # 保存说话者音频
                    speaker_filename = f"{safe_name}_speaker_{speaker_id}.wav"
                    speaker_path = os.path.join(output_dir, speaker_filename)
                    
                    import soundfile as sf
                    sf.write(speaker_path, combined_audio, sr)
                    
                    speaker_segments[speaker_id] = {
                        "audio_path": speaker_path,
                        "segment_count": len(segments),
                        "total_duration": sum(seg["end"] - seg["start"] for seg in segments),
                        "segments": segments
                    }
            
            result = {
                "success": True,
                "input_path": audio_path,
                "output_dir": output_dir,
                "speaker_count": len(speaker_segments),
                "speaker_segments": speaker_segments,
                "processing_info": {
                    "model": self.model_name,
                    "min_speakers": self.min_speakers,
                    "max_speakers": self.max_speakers
                }
            }
            
            self.logger.info(f"音频切分完成，识别到 {len(speaker_segments)} 个说话者")
            return result
            
        except Exception as e:
            self.logger.error(f"音频切分失败: {e}")
            raise
    
    def _process_diarization_result(self, diarization, audio_path: str, 
                                  output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        处理分离结果
        
        Args:
            diarization: pyannote分离结果
            audio_path: 音频文件路径
            output_dir: 输出目录
            
        Returns:
            处理后的分离结果
        """
        # 提取说话者信息
        speaker_segments = {}
        speaker_stats = {}
        
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_id = str(speaker)
            
            if speaker_id not in speaker_segments:
                speaker_segments[speaker_id] = []
                speaker_stats[speaker_id] = {
                    "segment_count": 0,
                    "total_duration": 0.0,
                    "first_appearance": turn.start,
                    "last_appearance": turn.end
                }
            
            segment_info = {
                "start": turn.start,
                "end": turn.end,
                "duration": turn.end - turn.start
            }
            
            speaker_segments[speaker_id].append(segment_info)
            speaker_stats[speaker_id]["segment_count"] += 1
            speaker_stats[speaker_id]["total_duration"] += segment_info["duration"]
            speaker_stats[speaker_id]["last_appearance"] = turn.end
        
        # 创建输出目录
        if output_dir:
            create_output_dir(output_dir)
            
            # 保存分离结果
            input_name = Path(audio_path).stem
            safe_name = safe_filename(input_name)
            
            # 保存详细结果
            result_file = os.path.join(output_dir, f"{safe_name}_diarization.txt")
            with open(result_file, 'w', encoding='utf-8') as f:
                f.write(f"说话人分离结果 - {input_name}\n")
                f.write("=" * 50 + "\n\n")
                
                for speaker_id, stats in speaker_stats.items():
                    f.write(f"说话者 {speaker_id}:\n")
                    f.write(f"  片段数量: {stats['segment_count']}\n")
                    f.write(f"  总时长: {stats['total_duration']:.2f}秒\n")
                    f.write(f"  首次出现: {stats['first_appearance']:.2f}秒\n")
                    f.write(f"  最后出现: {stats['last_appearance']:.2f}秒\n")
                    f.write(f"  平均片段时长: {stats['total_duration']/stats['segment_count']:.2f}秒\n\n")
                    
                    f.write("  详细片段:\n")
                    for i, segment in enumerate(speaker_segments[speaker_id]):
                        f.write(f"    {i+1}. [{segment['start']:.2f}s - {segment['end']:.2f}s] "
                               f"({segment['duration']:.2f}s)\n")
                    f.write("\n")
        else:
            result_file = None
        
        return {
            "success": True,
            "audio_path": audio_path,
            "result_file": result_file,
            "speaker_count": len(speaker_segments),
            "speaker_segments": speaker_segments,
            "speaker_stats": speaker_stats,
            "processing_info": {
                "model": self.model_name,
                "min_speakers": self.min_speakers,
                "max_speakers": self.max_speakers,
                "total_segments": sum(len(segs) for segs in speaker_segments.values())
            }
        }
    
    def get_speaker_embeddings(self, audio_path: str, speaker_segments: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取说话者嵌入向量
        
        Args:
            audio_path: 音频文件路径
            speaker_segments: 说话者片段信息
            
        Returns:
            嵌入向量字典
        """
        self.logger.info("开始提取说话者嵌入向量")
        
        try:
            # 加载音频
            audio, sr = librosa.load(audio_path, sr=16000)
            
            embeddings = {}
            
            for speaker_id, segments in speaker_segments.items():
                # 提取该说话者的所有音频片段
                speaker_audio_segments = []
                
                for segment in segments:
                    start_sample = int(segment["start"] * sr)
                    end_sample = int(segment["end"] * sr)
                    segment_audio = audio[start_sample:end_sample]
                    speaker_audio_segments.append(segment_audio)
                
                # 合并音频并提取特征
                if speaker_audio_segments:
                    combined_audio = np.concatenate(speaker_audio_segments)
                    
                    # 提取MFCC特征作为嵌入向量
                    mfcc = librosa.feature.mfcc(y=combined_audio, sr=sr, n_mfcc=13)
                    mean_mfcc = np.mean(mfcc, axis=1)
                    
                    embeddings[speaker_id] = {
                        "mfcc_mean": mean_mfcc.tolist(),
                        "audio_duration": len(combined_audio) / sr,
                        "segment_count": len(segments)
                    }
            
            self.logger.info(f"成功提取 {len(embeddings)} 个说话者的嵌入向量")
            return embeddings
            
        except Exception as e:
            self.logger.error(f"嵌入向量提取失败: {e}")
            raise
    
    def analyze_speaker_similarity(self, embeddings: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析说话者相似性
        
        Args:
            embeddings: 说话者嵌入向量
            
        Returns:
            相似性分析结果
        """
        self.logger.info("开始分析说话者相似性")
        
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            
            speaker_ids = list(embeddings.keys())
            similarity_matrix = np.zeros((len(speaker_ids), len(speaker_ids)))
            
            # 计算相似性矩阵
            for i, speaker1 in enumerate(speaker_ids):
                for j, speaker2 in enumerate(speaker_ids):
                    if i == j:
                        similarity_matrix[i][j] = 1.0
                    else:
                        emb1 = np.array(embeddings[speaker1]["mfcc_mean"]).reshape(1, -1)
                        emb2 = np.array(embeddings[speaker2]["mfcc_mean"]).reshape(1, -1)
                        similarity = cosine_similarity(emb1, emb2)[0][0]
                        similarity_matrix[i][j] = similarity
            
            # 分析结果
            analysis = {
                "similarity_matrix": similarity_matrix.tolist(),
                "speaker_ids": speaker_ids,
                "max_similarity": float(np.max(similarity_matrix[similarity_matrix != 1.0])),
                "min_similarity": float(np.min(similarity_matrix[similarity_matrix != 1.0])),
                "average_similarity": float(np.mean(similarity_matrix[similarity_matrix != 1.0]))
            }
            
            self.logger.info("说话者相似性分析完成")
            return analysis
            
        except Exception as e:
            self.logger.error(f"相似性分析失败: {e}")
            raise
    
    def _simple_speaker_diarization(self, audio_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        基于音频特征的简单说话人分离
        
        Args:
            audio_path: 音频文件路径
            output_dir: 输出目录
            
        Returns:
            分离结果字典
        """
        try:
            # 加载音频
            wav = preprocess_wav(audio_path)
            
            # 将音频分段（每段1秒）
            segment_duration = 1.0  # 秒
            segment_samples = int(segment_duration * sampling_rate)
            
            segments = []
            for i in range(0, len(wav), segment_samples):
                segment = wav[i:i + segment_samples]
                if len(segment) > segment_samples // 2:  # 至少1秒
                    segments.append({
                        "audio": segment,
                        "start_time": i / sampling_rate,
                        "end_time": (i + len(segment)) / sampling_rate
                    })
            
            # 提取每个片段的语音嵌入
            embeddings = []
            for segment in segments:
                embedding = self.encoder.embed_utterance(segment["audio"])
                embeddings.append(embedding)
            
            # 基于嵌入相似性进行说话人分离
            speaker_segments = self._cluster_speakers(segments, embeddings)
            
            # 处理结果
            result = self._process_simple_diarization_result(speaker_segments, audio_path, output_dir)
            
            return result
            
        except Exception as e:
            self.logger.error(f"简单说话人分离失败: {e}")
            raise
    
    def _cluster_speakers(self, segments: List[Dict], embeddings: List[np.ndarray]) -> Dict[str, List[Dict]]:
        """
        基于嵌入向量聚类说话者
        
        Args:
            segments: 音频片段列表
            embeddings: 对应的嵌入向量列表
            
        Returns:
            说话者片段字典
        """
        from sklearn.cluster import KMeans
        from sklearn.metrics.pairwise import cosine_similarity
        
        # 计算相似性矩阵
        similarity_matrix = cosine_similarity(embeddings)
        
        # 估计说话者数量（基于相似性阈值）
        threshold = 0.5  # 降低相似性阈值，更敏感
        n_speakers = self._estimate_speaker_count(similarity_matrix, threshold)
        
        # 使用K-means聚类
        if n_speakers > 1:
            kmeans = KMeans(n_clusters=n_speakers, random_state=42)
            speaker_labels = kmeans.fit_predict(embeddings)
        else:
            speaker_labels = [0] * len(segments)
        
        # 组织结果
        speaker_segments = {}
        for i, (segment, label) in enumerate(zip(segments, speaker_labels)):
            speaker_id = f"speaker_{label}"
            if speaker_id not in speaker_segments:
                speaker_segments[speaker_id] = []
            
            speaker_segments[speaker_id].append({
                "start": segment["start_time"],
                "end": segment["end_time"],
                "duration": segment["end_time"] - segment["start_time"],
                "embedding": embeddings[i].tolist()
            })
        
        return speaker_segments
    
    def _estimate_speaker_count(self, similarity_matrix: np.ndarray, threshold: float) -> int:
        """
        估计说话者数量
        
        Args:
            similarity_matrix: 相似性矩阵
            threshold: 相似性阈值
            
        Returns:
            估计的说话者数量
        """
        # 简单的启发式方法：基于相似性分布
        similarities = similarity_matrix[np.triu_indices_from(similarity_matrix, k=1)]
        
        # 如果大部分相似性都很高，可能是单说话者
        high_similarity_ratio = np.mean(similarities > threshold)
        
        if high_similarity_ratio > 0.9:
            return 1
        elif high_similarity_ratio > 0.7:
            return 2
        else:
            return min(3, self.max_speakers)
    
    def _process_simple_diarization_result(self, speaker_segments: Dict[str, List[Dict]], 
                                         audio_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        处理简单分离结果
        
        Args:
            speaker_segments: 说话者片段字典
            audio_path: 音频文件路径
            output_dir: 输出目录
            
        Returns:
            处理后的分离结果
        """
        # 计算统计信息
        speaker_stats = {}
        for speaker_id, segments in speaker_segments.items():
            total_duration = sum(seg["duration"] for seg in segments)
            speaker_stats[speaker_id] = {
                "segment_count": len(segments),
                "total_duration": total_duration,
                "first_appearance": min(seg["start"] for seg in segments),
                "last_appearance": max(seg["end"] for seg in segments)
            }
        
        # 创建输出目录
        if output_dir:
            create_output_dir(output_dir)
            
            # 保存分离结果
            input_name = Path(audio_path).stem
            safe_name = safe_filename(input_name)
            
            result_file = os.path.join(output_dir, f"{safe_name}_simple_diarization.txt")
            with open(result_file, 'w', encoding='utf-8') as f:
                f.write(f"简单说话人分离结果 - {input_name}\n")
                f.write("=" * 50 + "\n\n")
                
                for speaker_id, stats in speaker_stats.items():
                    f.write(f"说话者 {speaker_id}:\n")
                    f.write(f"  片段数量: {stats['segment_count']}\n")
                    f.write(f"  总时长: {stats['total_duration']:.2f}秒\n")
                    f.write(f"  首次出现: {stats['first_appearance']:.2f}秒\n")
                    f.write(f"  最后出现: {stats['last_appearance']:.2f}秒\n\n")
        else:
            result_file = None
        
        return {
            "success": True,
            "audio_path": audio_path,
            "result_file": result_file,
            "speaker_count": len(speaker_segments),
            "speaker_segments": speaker_segments,
            "speaker_stats": speaker_stats,
            "processing_info": {
                "method": "simple_clustering",
                "min_speakers": self.min_speakers,
                "max_speakers": self.max_speakers
            }
        }
