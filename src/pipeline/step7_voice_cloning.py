"""
步骤7: 音色克隆
音色克隆
"""

import os
from typing import Dict, Any
from ..output_manager import OutputManager, StepNumbers
from .base_step import BaseStep
from .processing_context import ProcessingContext


class Step7VoiceCloning(BaseStep):
    """步骤7: 音色克隆"""
    
    def execute(self) -> Dict[str, Any]:
        """执行步骤7: 音色克隆"""
        
        # 读取输入segments文件
        segments_with_audio_file = os.path.join(self.task_dir, "06_segments_with_audio.json")
        if not os.path.exists(segments_with_audio_file):
            return {
                "success": False,
                "error": f"输入segments文件不存在: {segments_with_audio_file}"
            }
        
        segments = self.read_json("06_segments_with_audio.json")
        
        # 获取预加载的模型或创建新实例
        voice_cloner = self.get_model("IndexTTS2")
        if voice_cloner is None:
            from ..voice_cloner import VoiceCloner
            voice_cloner = VoiceCloner(self.config)
        
        # 使用并行克隆方法
        cloning_result = voice_cloner.clone_segments_parallel(segments, self.output_manager)
        
        if not cloning_result.get("success", False):
            return {
                "success": False,
                "error": cloning_result.get("error", "音色克隆失败")
            }
        
        # 保存克隆结果元数据
        cloning_result_file = os.path.join(self.task_dir, "07_cloning_result.json")
        self.write_json(os.path.basename(cloning_result_file), cloning_result)
        
        self.logger.info(f'音色克隆完成: {cloning_result.get("cloned_segments", 0)}/{cloning_result.get("total_segments", 0)} 个片段成功')
        self.output_manager.log(f"步骤7完成: 音色克隆完成，{cloning_result.get('cloned_segments', 0)}/{cloning_result.get('total_segments', 0)} 个片段成功")
        
        return {
            "success": True,
            "cloning_result": cloning_result,
            "cloning_result_file": "07_cloning_result.json"
        }

