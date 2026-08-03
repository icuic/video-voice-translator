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

        # #region debug-point A:step7-entry
        import json, urllib.request, os as _os; _p='.dbg/voice-clone-page-close.env'; _u,_s='http://127.0.0.1:7778/event','voice-clone-page-close'; _r=_os.getenv('TRAE_DEBUG_RUN_ID','pre-fix'); exec("try:\n with open(_p) as f: c=f.read(); _u=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SERVER_URL=')),_u); _s=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SESSION_ID=')),_s)\nexcept: pass"); 
        try: urllib.request.urlopen(urllib.request.Request(_u, data=json.dumps({"sessionId":_s,"runId":_r,"hypothesisId":"A","location":"src/pipeline/step7_voice_cloning.py:execute:entry","msg":"[DEBUG] step7 voice cloning entry","data":{"task_dir":getattr(self,'task_dir',None),"segments_file":os.path.join(getattr(self,'task_dir',''),"06_segments_with_audio.json")}}).encode(), headers={"Content-Type":"application/json"}), timeout=2).read()
        except Exception: pass
        # #endregion
        
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

        # #region debug-point A:step7-model-ready
        import json, urllib.request, os as _os; _p='.dbg/voice-clone-page-close.env'; _u,_s='http://127.0.0.1:7778/event','voice-clone-page-close'; _r=_os.getenv('TRAE_DEBUG_RUN_ID','pre-fix'); exec("try:\n with open(_p) as f: c=f.read(); _u=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SERVER_URL=')),_u); _s=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SESSION_ID=')),_s)\nexcept: pass"); 
        try: urllib.request.urlopen(urllib.request.Request(_u, data=json.dumps({"sessionId":_s,"runId":_r,"hypothesisId":"A","location":"src/pipeline/step7_voice_cloning.py:execute:model","msg":"[DEBUG] step7 model instance ready","data":{"segments_count":len(segments) if isinstance(segments,list) else None}}).encode(), headers={"Content-Type":"application/json"}), timeout=2).read()
        except Exception: pass
        # #endregion
        
        # 定义进度回调函数
        def progress_callback(progress_pct, message, current_segment=0, total_segments=0):
            """步骤7内部进度回调"""
            # 获取全局进度回调（如果存在）
            global_progress_callback = getattr(self.context, 'progress_callback', None)
            if global_progress_callback:
                # 使用固定的步骤索引7（音色克隆）和步骤名称
                # 全局进度回调会自动根据步骤名称计算正确的索引
                global_progress_callback(7, "步骤7: 音色克隆", progress_pct, message, current_segment, total_segments)

        # 使用并行克隆方法，传入进度回调
        cloning_result = voice_cloner.clone_segments_parallel(segments, self.output_manager, progress_callback)

        # #region debug-point A:step7-clone-return
        import json, urllib.request, os as _os; _p='.dbg/voice-clone-page-close.env'; _u,_s='http://127.0.0.1:7778/event','voice-clone-page-close'; _r=_os.getenv('TRAE_DEBUG_RUN_ID','pre-fix'); exec("try:\n with open(_p) as f: c=f.read(); _u=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SERVER_URL=')),_u); _s=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SESSION_ID=')),_s)\nexcept: pass"); 
        try: urllib.request.urlopen(urllib.request.Request(_u, data=json.dumps({"sessionId":_s,"runId":_r,"hypothesisId":"A","location":"src/pipeline/step7_voice_cloning.py:execute:clone_return","msg":"[DEBUG] step7 clone_segments_parallel returned","data":{"success":bool(cloning_result.get("success")),"error":cloning_result.get("error"),"total_segments":cloning_result.get("total_segments"),"cloned_segments":cloning_result.get("cloned_segments"),"failed_segments":cloning_result.get("failed_segments")}}).encode(), headers={"Content-Type":"application/json"}), timeout=2).read()
        except Exception: pass
        # #endregion
        
        if not cloning_result.get("success", False):
            return {
                "success": False,
                "error": cloning_result.get("error", "音色克隆失败")
            }
        
        # 更新分段数据，添加克隆音频路径
        cloned_segments = cloning_result.get("cloned_segments", [])
        for i, cloned_segment in enumerate(cloned_segments):
            audio_path = cloned_segment.get("cloned_audio_path")
            if audio_path and i < len(segments):
                segments[i]["cloned_audio_path"] = audio_path

        # 保存更新后的分段数据
        translated_segments_file = os.path.join(self.task_dir, "05_translated_segments.json")
        self.write_json(os.path.basename(translated_segments_file), segments)
        self.logger.info(f"已更新分段文件: {translated_segments_file}")

        # 同步更新06文件，确保音频路径信息一致
        segments_with_audio_file = os.path.join(self.task_dir, "06_segments_with_audio.json")
        self.write_json(os.path.basename(segments_with_audio_file), segments)
        self.logger.info(f"已同步更新音频分段文件: {segments_with_audio_file}")

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
