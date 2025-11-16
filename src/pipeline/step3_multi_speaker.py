"""
步骤3: 多说话人处理
处理多说话人场景，生成说话人紧凑音轨和时间映射
"""

import os
import json
from typing import Dict, Any, Optional, List
from ..output_manager import OutputManager, StepNumbers
from .base_step import BaseStep
from .processing_context import ProcessingContext


class Step3MultiSpeaker(BaseStep):
    """步骤3: 多说话人处理"""
    
    def execute(self) -> Dict[str, Any]:
        """执行步骤3: 多说话人处理"""
        
        # 检查是否跳过（单说话人模式）
        if self.context.single_speaker:
            self.logger.info("用户指定仅一人说话，跳过说话人分离")
            self.output_manager.log("步骤3跳过: 用户指定仅一人说话")
            return {
                "success": True,
                "skipped": True,
                "reason": "single_speaker mode"
            }
        
        # 检查多说话人处理是否启用
        multi_speaker_enabled = bool(self.config.get("speaker_tracks", {}).get("enabled", False))
        if not multi_speaker_enabled:
            self.logger.info("多说话人处理未启用，跳过步骤3")
            self.output_manager.log("步骤3跳过: 多说话人处理未启用")
            return {
                "success": True,
                "skipped": True,
                "reason": "multi_speaker disabled"
            }
        
        # 读取输入人声文件
        vocals_path = self.output_manager.get_file_path(StepNumbers.STEP_2, "vocals")
        if not os.path.exists(vocals_path):
            return {
                "success": False,
                "error": f"输入人声文件不存在: {vocals_path}"
            }
        
        # 构建说话人音轨
        try:
            from ..pipeline.speaker_track_builder import SpeakerTrackBuilder
            builder = SpeakerTrackBuilder(self.config)
            tracks = builder.build(vocals_path, self.task_dir)
            
            if len(tracks) <= 1:
                self.logger.info("检测到单说话人或构建不足，跳过步骤3")
                self.output_manager.log("步骤3跳过: 检测到单说话人")
                return {
                    "success": True,
                    "skipped": True,
                    "reason": "single speaker detected",
                    "tracks_count": len(tracks)
                }
            
            # 保存tracks信息
            tracks_file = os.path.join(self.task_dir, "03_tracks.json")
            with open(tracks_file, 'w', encoding='utf-8') as f:
                json.dump(tracks, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"步骤3完成: 生成 {len(tracks)} 条说话人紧凑音轨")
            self.output_manager.log(f"步骤3完成: 生成 {len(tracks)} 条说话人紧凑音轨")
            
            return {
                "success": True,
                "tracks": tracks,
                "tracks_file": tracks_file,
                "tracks_count": len(tracks)
            }
            
        except Exception as e:
            self.logger.error(f"步骤3失败: {e}，将回退到单说话人处理")
            self.output_manager.log(f"步骤3失败: {e}，将回退到单说话人处理")
            return {
                "success": False,
                "error": str(e),
                "skipped": True,
                "reason": "error occurred"
            }

