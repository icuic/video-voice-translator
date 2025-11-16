"""
步骤6: 参考音频提取
提取参考音频片段
"""

import os
import json
import librosa
import soundfile as sf
from typing import Dict, Any, Optional, List
from ..output_manager import OutputManager, StepNumbers
from .base_step import BaseStep
from .processing_context import ProcessingContext


class Step6ReferenceAudio(BaseStep):
    """步骤6: 参考音频提取"""
    
    def execute(self) -> Dict[str, Any]:
        """执行步骤6: 参考音频提取"""
        
        # 读取输入segments文件
        translated_segments_file = os.path.join(self.task_dir, "05_translated_segments.json")
        if not os.path.exists(translated_segments_file):
            return {
                "success": False,
                "error": f"输入segments文件不存在: {translated_segments_file}"
            }
        
        segments = self.read_json("05_translated_segments.json")
        
        # 读取人声文件
        vocals_path = self.output_manager.get_file_path(StepNumbers.STEP_2, "vocals")
        if not os.path.exists(vocals_path):
            return {
                "success": False,
                "error": f"输入人声文件不存在: {vocals_path}"
            }
        
        # 检查是否有speaker_track_index（多说话人场景）
        speaker_track_index_file = os.path.join(self.task_dir, "04_speaker_track_index.json")
        speaker_track_index = None
        if os.path.exists(speaker_track_index_file):
            speaker_track_index = self.read_json("04_speaker_track_index.json")
        
        try:
            # 始终预加载完整人声，确保 sr 已初始化（供回退路径使用）
            vocals_audio, sr = librosa.load(vocals_path, sr=None)
            self.logger.info(f'预加载人声音频: {len(vocals_audio)} 样本, 采样率: {sr}Hz')
            
            # 若存在多说话人索引，准备按说话人紧凑音轨裁剪
            use_speaker_tracks = speaker_track_index is not None and len(speaker_track_index) > 0
            
            # 为每个分段提取并保存对应的音频片段
            for i, segment in enumerate(segments):
                start_time = segment.get("start", 0.0)
                end_time = segment.get("end", 0.0)
                spk_id = segment.get("speaker_id")
                
                if use_speaker_tracks and spk_id in speaker_track_index:
                    # 逆映射：全局时间 -> 紧凑时间，根据映射表线性换算（片段通常已不跨区间）
                    entry = speaker_track_index[spk_id]
                    spk_wav = entry["wav_path"]
                    mapping = entry["mapping"]
                    spk_audio, spk_sr = librosa.load(spk_wav, sr=None)
                    
                    comp_range = self._global_to_compact(start_time, end_time, mapping)
                    if comp_range is not None:
                        cs, ce = comp_range
                        cs_i = int(cs * spk_sr)
                        ce_i = int(ce * spk_sr)
                        cs_i = max(0, min(cs_i, len(spk_audio)))
                        ce_i = max(0, min(ce_i, len(spk_audio)))
                        if ce_i <= cs_i:
                            ce_i = min(len(spk_audio), cs_i + 1)
                        audio_segment = spk_audio[cs_i:ce_i]
                        sr = spk_sr
                    else:
                        # 回退：整段人声（使用已预加载的 vocals_audio 与 sr）
                        start_sample = int(start_time * sr)
                        end_sample = int(end_time * sr)
                        start_sample = max(0, min(start_sample, len(vocals_audio)-1))
                        end_sample = max(0, min(end_sample, len(vocals_audio)))
                        if end_sample <= start_sample:
                            end_sample = min(len(vocals_audio), start_sample + 1)
                        audio_segment = vocals_audio[start_sample:end_sample]
                else:
                    # 单说话人或无索引：使用完整人声裁剪
                    start_sample = int(start_time * sr)
                    end_sample = int(end_time * sr)
                    start_sample = max(0, min(start_sample, len(vocals_audio)-1))
                    end_sample = max(0, min(end_sample, len(vocals_audio)))
                    if end_sample <= start_sample:
                        end_sample = min(len(vocals_audio), start_sample + 1)
                    audio_segment = vocals_audio[start_sample:end_sample]
                
                # 保存音频片段
                ref_audio_path = self.output_manager.get_ref_segment_path(i)
                sf.write(ref_audio_path, audio_segment, sr)
                
                # 将参考音频路径添加到segment
                segment["audio_path"] = ref_audio_path
                
                if i < 5 or i % 10 == 0:  # 只显示前5个和每10个的进度
                    self.logger.info(f'分段 {i+1}: {start_time:.2f}s-{end_time:.2f}s -> {ref_audio_path}')
            
            # 保存包含audio_path的segments供步骤7使用
            segments_with_audio_file = os.path.join(self.task_dir, "06_segments_with_audio.json")
            self.write_json(os.path.basename(segments_with_audio_file), segments)
            
            self.output_manager.log(f"步骤6完成: 参考音频提取完成，{len(segments)} 个片段")
            
            return {
                "success": True,
                "segments": segments,
                "segments_with_audio_file": "06_segments_with_audio.json"
            }
            
        except Exception as e:
            self.logger.error(f'参考音频片段提取失败: {e}')
            # 如果提取失败，使用完整的人声文件作为备用
            self.logger.warning('使用完整人声文件作为备用参考音频...')
            for i, segment in enumerate(segments):
                segment["audio_path"] = vocals_path
            
            # 保存包含audio_path的segments供步骤7使用
            segments_with_audio_file = os.path.join(self.task_dir, "06_segments_with_audio.json")
            self.write_json(os.path.basename(segments_with_audio_file), segments)
            
            return {
                "success": False,
                "error": str(e),
                "segments": segments,
                "segments_with_audio_file": "06_segments_with_audio.json"
            }
    
    def _global_to_compact(self, gs: float, ge: float, mapping: List[Dict]) -> Optional[tuple]:
        """将全局时间映射到紧凑时间"""
        for m in mapping:
            gms, gme = float(m['global_start']), float(m['global_end'])
            if ge <= gms or gs >= gme:
                continue
            # 裁剪到该映射条目的重叠
            sub_gs = max(gs, gms)
            sub_ge = min(ge, gme)
            if sub_ge <= sub_gs or gme <= gms:
                continue
            cms, cme = float(m['compact_start']), float(m['compact_end'])
            # 线性映射
            ratio_s = (sub_gs - gms) / (gme - gms)
            ratio_e = (sub_ge - gms) / (gme - gms)
            cs = cms + ratio_s * (cme - cms)
            ce = cms + ratio_e * (cme - cms)
            return cs, ce
        return None

