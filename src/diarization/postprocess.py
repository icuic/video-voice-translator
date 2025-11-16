"""
说话人切分结果后处理：合并短间隙、过滤极短段、边界 padding
输入/输出: List[{start, end, speaker_id, confidence}]
"""

from typing import List, Dict, Any


def postprocess_segments(
    segments: List[Dict[str, Any]],
    merge_gap_ms: int = 250,
    min_duration_ms: int = 400,
    pad_ms: int = 120,
) -> List[Dict[str, Any]]:
    if not segments:
        return segments

    # 按时间排序
    segs = sorted(segments, key=lambda x: (x.get("start", 0.0), x.get("end", 0.0)))

    # 合并同 speaker 的近邻小间隙
    merged: List[Dict[str, Any]] = []
    for seg in segs:
        if not merged:
            merged.append(seg.copy())
            continue
        prev = merged[-1]
        if prev.get("speaker_id") == seg.get("speaker_id"):
            gap = max(0.0, float(seg.get("start", 0.0)) - float(prev.get("end", 0.0)))
            if gap * 1000.0 <= merge_gap_ms:
                prev["end"] = max(float(prev.get("end", 0.0)), float(seg.get("end", 0.0)))
                prev["confidence"] = min(prev.get("confidence", 1.0), seg.get("confidence", 1.0))
                continue
        merged.append(seg.copy())

    # 过滤过短段（并尝试并入相邻）
    filtered: List[Dict[str, Any]] = []
    for seg in merged:
        dur_ms = (float(seg.get("end", 0.0)) - float(seg.get("start", 0.0))) * 1000.0
        if dur_ms < min_duration_ms and filtered:
            # 并入前一个段的末尾
            filtered[-1]["end"] = max(float(filtered[-1]["end"]), float(seg.get("end", 0.0)))
            filtered[-1]["confidence"] = min(filtered[-1].get("confidence", 1.0), seg.get("confidence", 1.0))
        else:
            filtered.append(seg)

    # 边界 padding（不改重叠关系，仅微扩展）
    if pad_ms > 0:
        pad_s = pad_ms / 1000.0
        for i, seg in enumerate(filtered):
            seg["start"] = max(0.0, float(seg.get("start", 0.0)) - pad_s)
            seg["end"] = max(seg["start"], float(seg.get("end", 0.0)) + pad_s)

    return filtered


