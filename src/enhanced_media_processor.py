"""
增强的媒体处理器模块
集成音频分离功能的媒体处理器
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from .media_processor import MediaProcessor
from .audio_separator import AudioSeparator
from .audio_merger import AudioMerger
from .output_manager import OutputManager, StepNumbers
from .utils import validate_file_path, create_output_dir, safe_filename


class EnhancedMediaProcessor(MediaProcessor):
    """增强的媒体处理器类，支持音频分离功能"""

    def __init__(self, config_path_or_dict = "config.yaml"):
        super().__init__(config_path_or_dict)
        self.audio_separator = AudioSeparator(self.config)
        self.audio_merger = AudioMerger(self.config)
        self.enable_separation = self.config.get("defaults", {}).get("enable_separation", True)
        self.logger.info("增强媒体处理器初始化完成")

    def process_with_output_manager(self, input_path: str, output_manager: OutputManager,
                                   language: Optional[str] = None,
                                   force_separation: bool = False,
                                   progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        self.logger.info(f"开始增强处理: {input_path}")

        # #region debug-point A:enhanced-media-entry
        import json, urllib.request, os as _os; _p='.dbg/audio-extract-stuck.env'; _u,_s='http://127.0.0.1:7777/event','audio-extract-stuck'; _r=_os.getenv('TRAE_DEBUG_RUN_ID','pre-fix'); exec("try:\n with open(_p) as f: c=f.read(); _u=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SERVER_URL=')),_u); _s=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SESSION_ID=')),_s)\nexcept: pass"); 
        try: urllib.request.urlopen(urllib.request.Request(_u, data=json.dumps({"sessionId":_s,"runId":_r,"hypothesisId":"A","location":"src/enhanced_media_processor.py:process_with_output_manager:entry","msg":"[DEBUG] enhanced media processor entry","data":{"input_path":input_path}}).encode(), headers={"Content-Type":"application/json"}), timeout=2).read()
        except Exception: pass
        # #endregion

        if not validate_file_path(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        if language is None:
            language = self.default_language

        try:
            self.logger.info("执行基础媒体处理...")
            audio_path = output_manager.get_file_path(StepNumbers.STEP_1, "audio")

            # #region debug-point A:audio-extract-call
            import json, urllib.request, os as _os; _p='.dbg/audio-extract-stuck.env'; _u,_s='http://127.0.0.1:7777/event','audio-extract-stuck'; _r=_os.getenv('TRAE_DEBUG_RUN_ID','pre-fix'); exec("try:\n with open(_p) as f: c=f.read(); _u=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SERVER_URL=')),_u); _s=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SESSION_ID=')),_s)\nexcept: pass"); 
            try: urllib.request.urlopen(urllib.request.Request(_u, data=json.dumps({"sessionId":_s,"runId":_r,"hypothesisId":"A","location":"src/enhanced_media_processor.py:audio_extractor.extract:before","msg":"[DEBUG] calling audio_extractor.extract","data":{"input_path":input_path,"audio_path":audio_path,"has_progress_cb":bool(progress_callback)}}).encode(), headers={"Content-Type":"application/json"}), timeout=2).read()
            except Exception: pass
            # #endregion
            audio_result = self.audio_extractor.extract(input_path, audio_path, progress_callback)
            output_manager.log(f"步骤1完成: 音频已提取到 {audio_path}")

            # #region debug-point A:audio-extract-return
            import json, urllib.request, os as _os; _p='.dbg/audio-extract-stuck.env'; _u,_s='http://127.0.0.1:7777/event','audio-extract-stuck'; _r=_os.getenv('TRAE_DEBUG_RUN_ID','pre-fix'); exec("try:\n with open(_p) as f: c=f.read(); _u=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SERVER_URL=')),_u); _s=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SESSION_ID=')),_s)\nexcept: pass"); 
            try: urllib.request.urlopen(urllib.request.Request(_u, data=json.dumps({"sessionId":_s,"runId":_r,"hypothesisId":"A","location":"src/enhanced_media_processor.py:audio_extractor.extract:after","msg":"[DEBUG] audio_extractor.extract returned","data":{"success":bool(audio_result.get("success")),"extraction_type":audio_result.get("extraction_type"),"duration":audio_result.get("duration"),"output_size":audio_result.get("output_size")}}).encode(), headers={"Content-Type":"application/json"}), timeout=2).read()
            except Exception: pass
            # #endregion

            separation_needed = False
            separation_result = None
            detection_result = {"has_background_music": False}

            if self.enable_separation or force_separation:
                self.logger.info("检测背景音乐...")
                detection_result = self.audio_separator.detect_background_music(audio_path)
                if detection_result["has_background_music"]:
                    self.logger.info("检测到背景音乐，开始分离...")
                    vocals_path = output_manager.get_file_path(StepNumbers.STEP_2, "vocals")
                    accompaniment_path = output_manager.get_file_path(StepNumbers.STEP_2, "accompaniment")
                    separation_result = self.audio_separator.separate_audio_with_paths(
                        audio_path, vocals_path, accompaniment_path
                    )
                    separation_needed = True
                    output_manager.log("步骤2完成: 音频分离完成")
                    output_manager.log(f"  - 人声: {vocals_path}")
                    output_manager.log(f"  - 背景: {accompaniment_path}")
                else:
                    self.logger.info("未检测到背景音乐，跳过分离步骤")
                    output_manager.log("步骤2跳过: 未检测到背景音乐")

            enhanced_result = {
                "success": True,
                "input_path": input_path,
                "task_dir": output_manager.task_dir,
                "language": language,
                "audio_path": audio_path,
                "separation_needed": separation_needed,
                "separation_result": separation_result,
                "processing_info": {
                    "input_size": os.path.getsize(input_path),
                    "output_size": audio_result["output_size"],
                    "separation_enabled": separation_needed,
                    "has_background_music": detection_result["has_background_music"]
                }
            }

            if separation_needed and separation_result:
                enhanced_result.update({
                    "vocals_path": separation_result["vocals_path"],
                    "accompaniment_path": separation_result["accompaniment_path"],
                    "separation_quality": separation_result["separation_quality"]
                })

            output_manager.log("增强处理完成")
            return enhanced_result

        except Exception as e:
            self.logger.error(f"增强处理失败: {e}")
            output_manager.log(f"处理失败: {e}")

            # #region debug-point B:enhanced-media-exception
            import json, urllib.request, os as _os; _p='.dbg/audio-extract-stuck.env'; _u,_s='http://127.0.0.1:7777/event','audio-extract-stuck'; _r=_os.getenv('TRAE_DEBUG_RUN_ID','pre-fix'); exec("try:\n with open(_p) as f: c=f.read(); _u=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SERVER_URL=')),_u); _s=next((l.split('=',1)[1] for l in c.split('\\n') if l.startswith('DEBUG_SESSION_ID=')),_s)\nexcept: pass"); 
            try: urllib.request.urlopen(urllib.request.Request(_u, data=json.dumps({"sessionId":_s,"runId":_r,"hypothesisId":"B","location":"src/enhanced_media_processor.py:process_with_output_manager:except","msg":"[DEBUG] enhanced media exception","data":{"error":str(e)}}).encode(), headers={"Content-Type":"application/json"}), timeout=2).read()
            except Exception: pass
            # #endregion
            return {
                "success": False,
                "error": str(e),
                "input_path": input_path,
                "audio_path": None,
                "separation_needed": False,
                "separation_result": None
            }
