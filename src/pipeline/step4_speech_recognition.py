"""
步骤4: 语音识别
语音识别和分段优化
"""

import os
import json
from typing import Dict, Any, Optional, List
from ..output_manager import OutputManager, StepNumbers
from .base_step import BaseStep
from .processing_context import ProcessingContext


class Step4SpeechRecognition(BaseStep):
    """步骤4: 语音识别"""
    
    def execute(self) -> Dict[str, Any]:
        """执行步骤4: 语音识别"""
        
        # 读取输入人声文件
        vocals_path = self.output_manager.get_file_path(StepNumbers.STEP_2, "vocals")
        if not os.path.exists(vocals_path):
            return {
                "success": False,
                "error": f"输入人声文件不存在: {vocals_path}"
            }
        
        # 检查是否有tracks文件（多说话人场景）
        tracks_file = os.path.join(self.task_dir, "03_tracks.json")
        tracks = None
        if os.path.exists(tracks_file):
            tracks = self.read_json("03_tracks.json")
        
        # 获取预加载的模型或创建新实例
        whisper_processor = self.get_model("Whisper")
        if whisper_processor is None:
            from ..whisper_processor import WhisperProcessor
            whisper_processor = WhisperProcessor(self.config)
        
        # 统一ASR处理：支持单说话人和多说话人场景
        if tracks and len(tracks) > 1:
            # 多说话人场景：对每个说话人紧凑音轨分别运行ASR，然后合并
            self.logger.info("多说话人场景：对每个说话人音轨分别进行ASR...")
            
            combined_segments = []
            speaker_track_index = {}  # 用于步骤6的参考音频提取
            detected_language_for_result = None  # 保存检测到的语言，用于最终结果
            
            for t in tracks:
                spk_id = t.get('speaker_id')
                wav_path = t.get('wav_path')
                map_path = t.get('map_path')
                
                # 读取时间映射表
                with open(map_path, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                speaker_track_index[spk_id] = {"wav_path": wav_path, "mapping": mapping}
                
                # 对说话人紧凑音轨运行ASR
                self.logger.info(f"ASR处理说话人 {spk_id}...")
                
                # 语言检测
                detected_language = None
                if whisper_processor.language == "auto":
                    try:
                        detection_result = whisper_processor.detect_language(wav_path)
                        detected_language = detection_result.get("detected_language", "en")
                    except:
                        detected_language = "en"
                else:
                    detected_language = whisper_processor.language
                
                # 保存第一个说话人的语言检测结果
                if detected_language_for_result is None:
                    detected_language_for_result = detected_language
                
                # 调用内部转录方法
                if whisper_processor.backend == "faster-whisper":
                    temp_result = whisper_processor._transcribe_faster_whisper(wav_path, detected_language, None)
                else:
                    temp_result = whisper_processor.model.transcribe(
                        wav_path,
                        language=detected_language,
                        task=whisper_processor.task,
                        verbose=False,
                        word_timestamps=True,
                        initial_prompt=None,
                        condition_on_previous_text=False,
                        compression_ratio_threshold=1.2,
                        no_speech_threshold=0.2,
                    )
                
                # 保存说话人的ASR结果到speakers/<speaker_id>/目录
                self._save_speaker_asr_result(temp_result, spk_id)
                
                segs = temp_result.get('segments', [])
                
                # 映射并标注speaker
                for seg in segs:
                    cs = float(seg.get('start', 0.0))
                    ce = float(seg.get('end', cs))
                    words = seg.get('words', [])
                    pieces = self._split_and_map_segment(cs, ce, words, mapping)
                    
                    # 基于词重建文本；若无词则使用原文本
                    for p in pieces:
                        if p['words']:
                            # 简单拼接词，保持原序
                            text_rebuilt = ''.join([w.get('word', '') for w in p['words']]).strip()
                        else:
                            text_rebuilt = seg.get('text', '')
                        combined_segments.append({
                            "start": p['start'],
                            "end": p['end'],
                            "text": text_rebuilt,
                            "words": p['words'] if p['words'] else words,
                            "speaker_id": spk_id,
                        })
            
            # 按全局时间排序合并后的segments
            combined_segments = sorted(combined_segments, key=lambda x: (x['start'], x['end']))
            self.logger.info(f'合并完成：生成 {len(combined_segments)} 个带speaker的片段')
            
            # 对多说话人segments进行分段优化（按说话人分组优化）
            segmentation_config = self.config.get("whisper", {}).get("segmentation", {})
            segmentation_method = segmentation_config.get("method", "semantic")
            
            if segmentation_method in ["punctuation", "semantic"]:
                try:
                    optimized_segments = self._optimize_multi_speaker_segments(
                        combined_segments, whisper_processor, segmentation_method
                    )
                    combined_segments = optimized_segments
                    segment_optimized = True
                    self.logger.info(f'分段优化完成：{len(combined_segments)} 个优化片段')
                except Exception as e:
                    self.logger.warning(f'分段优化失败：{e}，使用原始分段')
                    segment_optimized = False
            else:
                segment_optimized = False
            
            # 保存为04_segments.json
            segments_json_file = self.output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
            self.write_json(os.path.basename(segments_json_file), combined_segments)
            
            # 保存为04_segments.txt（可读格式）
            segments_txt_file = self.output_manager.get_file_path(StepNumbers.STEP_4, "segments_txt")
            with open(segments_txt_file, 'w', encoding='utf-8') as f:
                for i, seg in enumerate(combined_segments):
                    speaker_info = f" [speaker: {seg.get('speaker_id', 'unknown')}]" if seg.get('speaker_id') else ""
                    f.write(f"Segment {i+1} ({seg['start']:.3f}s - {seg['end']:.3f}s){speaker_info}:\n")
                    f.write(f"{seg['text']}\n\n")
            
            # 保存转录文本
            transcription_file = self.output_manager.get_file_path(StepNumbers.STEP_4, "whisper_raw_transcription")
            full_text = ' '.join([seg['text'] for seg in combined_segments])
            with open(transcription_file, 'w', encoding='utf-8') as f:
                f.write(full_text)
            
            # 保存speaker_track_index供步骤6使用
            speaker_track_index_file = os.path.join(self.task_dir, "04_speaker_track_index.json")
            with open(speaker_track_index_file, 'w', encoding='utf-8') as f:
                json.dump(speaker_track_index, f, ensure_ascii=False, indent=2)
            
            # 构造transcription_result供后续步骤使用
            transcription_result = {
                "success": True,
                "segments": combined_segments,
                "language": detected_language_for_result or 'unknown',
                "processing_info": {
                    "multi_speaker": True,
                    "speakers_count": len(tracks),
                    "segment_optimized": segment_optimized
                }
            }
            
            self.output_manager.log(f"步骤4完成：多说话人ASR完成，{len(combined_segments)} 个片段")
            
        else:
            # 单说话人场景：直接对02_vocals.wav运行ASR
            transcription_result = whisper_processor.transcribe_with_output_manager(vocals_path, self.output_manager)
            speaker_track_index = None
        
        if not transcription_result.get("success"):
            return {
                "success": False,
                "error": transcription_result.get("error", "语音识别失败")
            }
        
        segments = transcription_result.get("segments", [])
        self.logger.info(f'识别到 {len(segments)} 个片段')
        
        # 保存原始分段数据供后续验证使用（如果启用了暂停功能）
        if self.context.pause_after_step4:
            original_segments_file = os.path.join(self.task_dir, "04_segments_original.json")
            with open(original_segments_file, 'w', encoding='utf-8') as f:
                json.dump(segments, f, ensure_ascii=False, indent=2)
            self.logger.info(f"已保存原始分段数据: {original_segments_file}")
        
        return {
            "success": True,
            "segments": segments,
            "language": transcription_result.get("language", "unknown"),
            "processing_info": transcription_result.get("processing_info", {}),
            "speaker_track_index_file": "04_speaker_track_index.json" if tracks and len(tracks) > 1 else None,
            "needs_editing": self.context.pause_after_step4  # 标记是否需要编辑
        }
    
    def _split_and_map_segment(self, cs: float, ce: float, words: list, mapping: List[Dict]) -> List[Dict]:
        """将紧凑段按映射区间切分，逐段映射回全局时间。返回 List[{start,end,words}]"""
        pieces = []
        # 遍历所有与 [cs,ce] 有交集的映射条目
        for m in mapping:
            ms, me = float(m['compact_start']), float(m['compact_end'])
            if me <= ms:
                continue
            # 交集
            sub_s = max(cs, ms)
            sub_e = min(ce, me)
            if sub_e <= sub_s:
                continue
            # 映射到全局
            gs, ge = float(m['global_start']), float(m['global_end'])
            # 线性映射
            ratio_s = (sub_s - ms) / (me - ms)
            ratio_e = (sub_e - ms) / (me - ms)
            g_sub_s = gs + ratio_s * (ge - gs)
            g_sub_e = gs + ratio_e * (ge - gs)
            
            # 选择属于该子区间的词
            sub_words = []
            if words:
                for w in words:
                    ws = float(w.get('start', sub_s))
                    we = float(w.get('end', ws))
                    # 词在紧凑时间轴内的重叠
                    if we > sub_s and ws < sub_e:
                        # 将词边界裁剪到子区间
                        adj_ws = max(ws, sub_s)
                        adj_we = min(we, sub_e)
                        # 映射到全局
                        w_ratio_s = (adj_ws - ms) / (me - ms)
                        w_ratio_e = (adj_we - ms) / (me - ms)
                        g_ws = gs + w_ratio_s * (ge - gs)
                        g_we = gs + w_ratio_e * (ge - gs)
                        sub_words.append({
                            **w,
                            'start': g_ws,
                            'end': g_we,
                        })
            
            pieces.append({
                'start': g_sub_s,
                'end': g_sub_e,
                'words': sub_words,
            })
        return pieces
    
    def _optimize_multi_speaker_segments(self, combined_segments: List[Dict], whisper_processor, segmentation_method: str) -> List[Dict]:
        """对多说话人segments进行分段优化"""
        # 1. 按speaker_id分组
        segments_by_speaker = {}
        for seg in combined_segments:
            speaker_id = seg.get('speaker_id')
            if speaker_id not in segments_by_speaker:
                segments_by_speaker[speaker_id] = []
            segments_by_speaker[speaker_id].append(seg)
        
        self.logger.info(f'按说话人分组：{len(segments_by_speaker)} 个说话人')
        
        # 2. 对每个说话人分别优化
        optimized_all = []
        for speaker_id, segs in segments_by_speaker.items():
            self.logger.info(f'优化说话人 {speaker_id}：{len(segs)} 个片段')
            
            if segmentation_method == "punctuation" and whisper_processor.segment_optimizer:
                # 使用punctuation方法优化
                word_timestamps = []
                transcription_texts = []
                for seg in segs:
                    word_timestamps.extend(seg.get('words', []))
                    transcription_texts.append(seg.get('text', ''))
                
                # 创建临时转录文件
                transcription_file = self.output_manager.get_file_path(StepNumbers.STEP_4, "whisper_raw_transcription")
                full_text = ' '.join(transcription_texts)
                with open(transcription_file, 'w', encoding='utf-8') as f:
                    f.write(full_text)
                
                # 优化分段
                optimized = whisper_processor.segment_optimizer.optimize_segments(
                    transcription_file, word_timestamps, speaker_id=speaker_id
                )
                
                # 确保所有优化后的segments都保留speaker_id
                for opt_seg in optimized:
                    if 'speaker_id' not in opt_seg:
                        opt_seg['speaker_id'] = speaker_id
                optimized_all.extend(optimized)
                
            elif segmentation_method == "semantic" and whisper_processor.semantic_segmenter:
                # 使用semantic方法优化
                all_words = []
                full_text_parts = []
                for seg in segs:
                    all_words.extend(seg.get('words', []))
                    full_text_parts.append(seg.get('text', ''))
                
                full_text = ' '.join(full_text_parts)
                
                # 优化分段
                optimized = whisper_processor.semantic_segmenter.segment(
                    all_words, full_text, speaker_id=speaker_id
                )
                
                # 确保所有优化后的segments都保留speaker_id
                for opt_seg in optimized:
                    if 'speaker_id' not in opt_seg:
                        opt_seg['speaker_id'] = speaker_id
                optimized_all.extend(optimized)
            else:
                # 不支持的分段方法或优化器不可用，使用原始segments
                optimized_all.extend(segs)
        
        # 3. 按全局时间重新排序
        optimized_all = sorted(optimized_all, key=lambda x: (x['start'], x['end']))
        
        return optimized_all
    
    def _save_speaker_asr_result(self, temp_result: Dict[str, Any], speaker_id: str) -> None:
        """保存说话人的ASR结果到speakers/<speaker_id>/目录"""
        speakers_dir = os.path.join(self.task_dir, "speakers")
        speaker_dir = os.path.join(speakers_dir, speaker_id)
        os.makedirs(speaker_dir, exist_ok=True)
        
        # 提取转录文本
        segments = temp_result.get('segments', [])
        text_parts = [seg.get('text', '') for seg in segments]
        text = ' '.join(text_parts).strip()
        
        # 1. 保存Whisper原始输出（JSON）
        raw_json_path = os.path.join(speaker_dir, f"{speaker_id}_04_whisper_raw.json")
        with open(raw_json_path, 'w', encoding='utf-8') as f:
            json.dump(temp_result, f, ensure_ascii=False, indent=2)
        
        # 2. 保存Whisper原始分段（可读格式）
        raw_segments_path = os.path.join(speaker_dir, f"{speaker_id}_04_whisper_raw_segments.txt")
        with open(raw_segments_path, 'w', encoding='utf-8') as f:
            f.write("Whisper 原始分段（紧凑时间）:\n")
            f.write("=" * 60 + "\n\n")
            for i, seg in enumerate(segments):
                f.write(f"分段 {i+1}:\n")
                f.write(f"  时间: {seg.get('start', 0):.3f}s - {seg.get('end', 0):.3f}s\n")
                f.write(f"  文本: {seg.get('text', '')}\n")
                f.write(f"  单词数: {len(seg.get('words', []))}\n\n")
        
        # 3. 保存转录文本
        transcription_path = os.path.join(speaker_dir, f"{speaker_id}_04_whisper_raw_transcription.txt")
        with open(transcription_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        # 4. 保存单词级时间戳（紧凑时间）
        word_timestamps = []
        for segment in segments:
            for word in segment.get('words', []):
                word_timestamps.append({
                    "word": word.get("word", ""),
                    "start": word.get("start", 0.0),
                    "end": word.get("end", 0.0),
                    "probability": word.get("probability", 0.0)
                })
        
        word_timestamps_path = os.path.join(speaker_dir, f"{speaker_id}_04_whisper_raw_word_timestamps.txt")
        with open(word_timestamps_path, 'w', encoding='utf-8') as f:
            f.write("Whisper 原始单词时间戳（紧凑时间）:\n")
            f.write("=" * 60 + "\n\n")
            for word_info in word_timestamps:
                f.write(f"{word_info['start']:.3f} - {word_info['end']:.3f}: {word_info['word']} (prob: {word_info['probability']:.3f})\n")

