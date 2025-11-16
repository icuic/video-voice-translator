"""
将 Whisper 分段绑定到说话人时间线；为每个 speaker 选择稳定参考音频
输出: 为每个段添加 {speaker_id, confidence, reference_audio_path}
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple

from ..diarization.pyannote_diarizer import PyannoteDiarizer
from ..diarization.postprocess import postprocess_segments


def _seg_times(seg: Dict[str, Any]) -> Tuple[float, float]:
    # 兼容 {start,end} 或 {start_time,end_time}
    s = float(seg.get("start", seg.get("start_time", 0.0)))
    e = float(seg.get("end", seg.get("end_time", max(s, 0.0))))
    if e < s:
        e = s
    return s, e


def _overlap(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


class SpeakerBinder:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.diarizer = PyannoteDiarizer(config)

        self.merge_gap_ms = config.get("diarization_post", {}).get("merge_gap_ms", 250)
        self.min_duration_ms = config.get("diarization_post", {}).get("min_duration_ms", 400)
        self.pad_ms = config.get("diarization_post", {}).get("pad_ms", 120)

    def bind(self, audio_path: Optional[str], segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        - 可选在整段音频上执行 diarization
        - 将每个 whisper 段绑定到重叠最大的话者
        - 为每个 speaker 选定稳定参考音频(reference_audio_path)
        """
        if not segments:
            return segments

        # 1) 取说话人时间线
        spk_timeline: List[Dict[str, Any]] = []
        if audio_path and os.path.exists(audio_path) and self.diarizer.enabled:
            raw = self.diarizer.diarize(audio_path)
            spk_timeline = postprocess_segments(
                raw, self.merge_gap_ms, self.min_duration_ms, self.pad_ms
            )
        else:
            # 不可用时，退化为单说话人 (speaker_0)
            s0, e0 = _seg_times(segments[0])
            sN, eN = _seg_times(segments[-1])
            spk_timeline = [{
                "start": min(s0, e0),
                "end": max(sN, eN),
                "speaker_id": "speaker_0",
                "confidence": 0.5
            }]

        # 2) 绑定每个分段到重叠最大的 speaker
        bound: List[Dict[str, Any]] = []
        for seg in segments:
            s, e = _seg_times(seg)
            best = None
            best_ov = 0.0
            for sp in spk_timeline:
                ov = _overlap((s, e), (float(sp["start"]), float(sp["end"])) )
                if ov > best_ov:
                    best_ov = ov
                    best = sp
            if best is None:
                # 兜底到第一个
                best = spk_timeline[0]
            seg2 = {**seg}
            seg2["speaker_id"] = best["speaker_id"]
            seg2["speaker_confidence"] = best.get("confidence", 1.0)
            # 标准化时间字段，补充 start_time/end_time
            seg2.setdefault("start_time", s)
            seg2.setdefault("end_time", e)
            bound.append(seg2)

        # 3) 为每个 speaker 选择一个稳定参考音频路径
        #    策略：优先选择该 speaker 下最长的、已有 audio_path 的段作为参考
        spk_best_ref: Dict[str, Tuple[float, str]] = {}
        for seg in bound:
            spk = seg.get("speaker_id", "speaker_0")
            audio_path_seg = seg.get("audio_path", "")
            s, e = _seg_times(seg)
            dur = max(0.0, e - s)
            if audio_path_seg and os.path.exists(audio_path_seg):
                best = spk_best_ref.get(spk)
                if best is None or dur > best[0]:
                    spk_best_ref[spk] = (dur, audio_path_seg)

        # 4) 回填 reference_audio_path（没有可用时，保留原有 audio_path）
        for seg in bound:
            spk = seg.get("speaker_id", "speaker_0")
            ref = spk_best_ref.get(spk, (0.0, seg.get("audio_path", "")))[1]
            if ref:
                seg["reference_audio_path"] = ref
        return bound


