"""
步骤3：按说话人生成紧凑音轨与时间映射（仅音频处理）
输入：02_vocals.wav
输出：speakers/<speaker_id>/<speaker_id>.wav 与 speakers/<speaker_id>/<speaker_id>.json（紧凑→全局时间映射）

注意：步骤3只负责音频处理（说话人分离、紧凑音轨生成、时间映射），
      不包含语音识别（ASR）。ASR处理统一在步骤4进行。
"""

import os
import json
import logging
from typing import Dict, Any, List

import numpy as np
import librosa
import soundfile as sf

from ..diarization.pyannote_diarizer import PyannoteDiarizer
from ..diarization.postprocess import postprocess_segments
from ..diarization.speaker_merger import SpeakerMerger


class SpeakerTrackBuilder:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.diarizer = PyannoteDiarizer(config)
        tracks_cfg = config.get("speaker_tracks", {})
        self.compact_concat: bool = tracks_cfg.get("compact_concat", True)
        self.min_gap_merge_ms: int = int(tracks_cfg.get("min_gap_merge_ms", 150))
        self.tse_enabled: bool = bool(tracks_cfg.get("tse", {}).get("enabled", False))

        # 可选TSE模块（占位/直通）
        try:
            from ..separation.tse import TargetSpeakerEnhancer
            self.tse = TargetSpeakerEnhancer(config)
        except Exception:
            self.tse = None
        
        # 相似度合并模块
        self.speaker_merger = SpeakerMerger(config)

    def build(self, vocals_wav: str, task_dir: str) -> List[Dict[str, Any]]:
        """基于 pyannote 结果，输出每位说话人的紧凑音轨与映射表。
        
        注意：此函数只负责音频处理（说话人分离和紧凑音轨生成），
        不包含语音识别（ASR）。ASR处理统一在步骤4进行。

        Returns: List[{speaker_id, wav_path, map_path}]
        """
        if not os.path.exists(vocals_wav):
            self.logger.warning(f"vocals wav 不存在: {vocals_wav}")
            return []

        # 1) 说话人时间线
        diar_segments = self.diarizer.diarize(vocals_wav)
        diar_segments = postprocess_segments(
            diar_segments,
            merge_gap_ms=self.min_gap_merge_ms,
            min_duration_ms=200,
            pad_ms=0,
        )
        if not diar_segments:
            self.logger.info("未获得说话人区间，返回空")
            return []
        
        # 1.5) 基于相似度的短片段合并
        if self.speaker_merger.enabled:
            try:
                original_count = len(set(seg.get("speaker_id") for seg in diar_segments))
                diar_segments = self.speaker_merger.merge_short_segments_by_similarity(
                    diar_segments, vocals_wav
                )
                merged_count = len(set(seg.get("speaker_id") for seg in diar_segments))
                if merged_count < original_count:
                    self.logger.info(f"相似度合并完成：说话人数量从 {original_count} 减少到 {merged_count}")
            except Exception as e:
                self.logger.warning(f"相似度合并失败，继续使用原始结果: {e}")

        # 聚合为 speaker -> 区间列表
        speaker_to_intervals: Dict[str, List[Dict[str, float]]] = {}
        for seg in diar_segments:
            spk = seg.get("speaker_id", "speaker_0")
            speaker_to_intervals.setdefault(spk, []).append({
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
            })
        speakers = list(speaker_to_intervals.keys())
        if len(speakers) == 1:
            self.logger.info("检测到单说话人，将在上层逻辑中绕过2.5")

        # 2) 加载整段人声
        audio, sr = librosa.load(vocals_wav, sr=None)

        # 输出目录
        speakers_dir = os.path.join(task_dir, "speakers")
        os.makedirs(speakers_dir, exist_ok=True)

        results: List[Dict[str, Any]] = []

        # 3) 为每位说话人拼接紧凑音轨并生成映射
        #    同时识别与统计重叠区，若启用TSE则对重叠区做目标增强
        #    简单重叠判定：任意其它说话人的区间与当前区间存在交集
        for spk in speakers:
            intervals = sorted(speaker_to_intervals[spk], key=lambda x: (x["start"], x["end"]))

            compact_chunks: List[np.ndarray] = []
            mapping: List[Dict[str, float]] = []

            compact_cursor = 0.0
            overlapped_total = 0.0
            kept_total = 0.0
            for itv in intervals:
                s = max(0.0, float(itv["start"]))
                e = max(s, float(itv["end"]))
                s_i = int(s * sr)
                e_i = int(e * sr)
                if e_i <= s_i or s_i >= len(audio):
                    continue
                e_i = min(e_i, len(audio))
                chunk = audio[s_i:e_i]

                # 判定是否重叠
                is_overlap = False
                for other_spk, other_ints in speaker_to_intervals.items():
                    if other_spk == spk:
                        continue
                    for oitv in other_ints:
                        os_, oe_ = float(oitv["start"]), float(oitv["end"])
                        if oe_ > s and os_ < e:
                            is_overlap = True
                            break
                    if is_overlap:
                        break

                # 可选：仅对重叠区做TSE增强
                if is_overlap and self.tse_enabled and self.tse is not None:
                    try:
                        chunk = self.tse.enhance_chunk(chunk, sr, spk)
                        # 记录掩膜统计（若可用）
                        stats = getattr(self.tse, 'last_mask_stats', {}) or {}
                        if stats:
                            self.logger.info(f"TSE[{spk}] overlap {s:.2f}-{e:.2f} mask_mean={stats.get('mask_mean'):.3f} std={stats.get('mask_std'):.3f}")
                    except Exception as _e:
                        self.logger.warning(f"TSE 失败 {spk} {s:.2f}-{e:.2f}: {_e}")

                kept_total += (e - s)
                if is_overlap:
                    overlapped_total += (e - s)

                compact_chunks.append(chunk)
                dur = len(chunk) / sr
                mapping.append({
                    "compact_start": float(compact_cursor),
                    "compact_end": float(compact_cursor + dur),
                    "global_start": float(s),
                    "global_end": float(e),
                })
                compact_cursor += dur

            if not compact_chunks:
                continue

            # 为每个说话人创建独立的子目录
            spk_dir = os.path.join(speakers_dir, spk)
            os.makedirs(spk_dir, exist_ok=True)

            compact_audio = np.concatenate(compact_chunks)
            # 紧凑音轨保存到 speakers/<speaker_id>/<speaker_id>.wav
            spk_wav = os.path.join(spk_dir, f"{spk}.wav")
            sf.write(spk_wav, compact_audio, sr)

            # 时间映射表保存到 speakers/<speaker_id>/<speaker_id>.json
            map_path = os.path.join(spk_dir, f"{spk}.json")
            with open(map_path, "w", encoding="utf-8") as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)

            results.append({
                "speaker_id": spk,
                "wav_path": spk_wav,
                "map_path": map_path,
            })

            # 简要重叠统计
            if kept_total > 0:
                ratio = overlapped_total / kept_total
                self.logger.info(f"步骤3: 说话人 {spk} 重叠占比 {ratio:.2%} ({overlapped_total:.2f}s/{kept_total:.2f}s)")

        self.logger.info(f"步骤3: 生成 {len(results)} 条说话人音轨")
        return results


