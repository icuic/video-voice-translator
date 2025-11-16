"""
步骤8: 音频合并
时间同步音频合并
"""

import os
from typing import Dict, Any
from ..output_manager import OutputManager, StepNumbers
from .base_step import BaseStep
from .processing_context import ProcessingContext


class Step8AudioMerging(BaseStep):
    """步骤8: 音频合并"""
    
    def execute(self) -> Dict[str, Any]:
        """执行步骤8: 音频合并"""
        
        # 读取克隆结果文件
        cloning_result_file = os.path.join(self.task_dir, "07_cloning_result.json")
        if not os.path.exists(cloning_result_file):
            return {
                "success": False,
                "error": f"克隆结果文件不存在: {cloning_result_file}"
            }
        
        cloning_result = self.read_json("07_cloning_result.json")
        
        # 检查克隆结果
        if not cloning_result.get("success", False):
            return {
                "success": False,
                "error": "语音克隆失败"
            }
        
        # 读取segments文件（用于获取音频路径）
        segments_with_audio_file = os.path.join(self.task_dir, "06_segments_with_audio.json")
        if not os.path.exists(segments_with_audio_file):
            return {
                "success": False,
                "error": f"segments文件不存在: {segments_with_audio_file}"
            }
        
        segments = self.read_json("06_segments_with_audio.json")
        
        # 读取原始人声文件（用于获取时长）
        vocals_path = self.output_manager.get_file_path(StepNumbers.STEP_2, "vocals")
        if not os.path.exists(vocals_path):
            return {
                "success": False,
                "error": f"原始人声文件不存在: {vocals_path}"
            }
        
        # 使用时间同步音频合并器
        from ..timestamped_audio_merger import TimestampedAudioMerger
        audio_merger = TimestampedAudioMerger(self.config)
        
        # 获取原始音频时长
        total_duration = audio_merger.get_original_audio_duration(vocals_path)
        
        if total_duration <= 0:
            return {
                "success": False,
                "error": "无法获取原始音频时长"
            }
        
        # 准备片段数据 - 使用翻译后的分段和对应的音频文件
        segments_for_merge = []
        for i, segment in enumerate(segments):
            # 获取对应的音频文件路径
            audio_file = self.output_manager.get_segment_path(i)
            if os.path.exists(audio_file):
                segments_for_merge.append({
                    "start": segment.get("start", 0.0),
                    "end": segment.get("end", 0.0),
                    "audio_path": audio_file,
                    "text": segment.get("translated_text", ""),
                    "original_text": segment.get("original_text", "")
                })
        
        # 创建时间同步音频轨道
        final_audio_path = self.output_manager.get_file_path(StepNumbers.STEP_8, "final_voice")
        
        merge_result = audio_merger.create_timestamped_audio_track_with_output_manager(
            segments_for_merge, 
            total_duration, 
            self.output_manager
        )
        
        if not merge_result.get("success"):
            return {
                "success": False,
                "error": merge_result.get("error", "时间同步音频合并失败")
            }
        
        # 更新final_audio_path为实际生成的路径
        final_audio_path = merge_result.get("output_path", final_audio_path)
        
        # 保存合并结果元数据
        merge_result_file = os.path.join(self.task_dir, "08_merge_result.json")
        merge_metadata = {
            "success": merge_result.get("success", False),
            "segments_processed": merge_result.get("segments_processed", 0),
            "total_duration": merge_result.get("total_duration", 0),
            "method": merge_result.get("method", "unknown"),
            "output_path": final_audio_path
        }
        self.write_json(os.path.basename(merge_result_file), merge_metadata)
        
        self.logger.info(f'时间同步音频合并完成: {final_audio_path}')
        self.logger.info(f'处理了 {merge_result.get("segments_processed", 0)} 个音频片段')
        self.logger.info(f'总时长: {merge_result.get("total_duration", 0):.1f}秒')
        self.logger.info(f'使用方法: {merge_result.get("method", "未知")}')
        self.output_manager.log(f"步骤8完成: 时间同步音频合并完成，{merge_result.get('segments_processed', 0)} 个片段")
        
        return {
            "success": True,
            "final_audio_path": final_audio_path,
            "merge_result": merge_metadata,
            "merge_result_file": "08_merge_result.json"
        }

