"""
步骤5: 文本翻译
文本翻译
"""

import os
from typing import Dict, Any, List
from ..output_manager import OutputManager, StepNumbers
from .base_step import BaseStep
from .processing_context import ProcessingContext


class Step5TextTranslation(BaseStep):
    """步骤5: 文本翻译"""
    
    def execute(self) -> Dict[str, Any]:
        """执行步骤5: 文本翻译"""
        
        # 读取输入segments文件
        segments_json_file = self.output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
        if not os.path.exists(segments_json_file):
            return {
                "success": False,
                "error": f"输入segments文件不存在: {segments_json_file}"
            }
        
        segments = self.read_json(os.path.basename(segments_json_file))
        
        # 验证分段数据（如果存在原始分段数据，进行对比验证）
        original_segments_file = os.path.join(self.task_dir, "04_segments_original.json")
        if os.path.exists(original_segments_file):
            try:
                from ..segment_editor import validate_segment_data, load_segments
                original_segments = load_segments(original_segments_file)
                
                # 收集所有单词用于验证
                all_words = []
                for seg in original_segments:
                    all_words.extend(seg.get('words', []))
                
                # 验证编辑后的分段数据
                is_valid, error_msg = validate_segment_data(segments, all_words)
                if not is_valid:
                    self.logger.warning(f"分段数据验证警告: {error_msg}")
                    # 不阻止继续，但记录警告
                else:
                    self.logger.info("分段数据验证通过")
            except Exception as e:
                self.logger.warning(f"分段数据验证失败: {e}，继续执行")
        
        # 翻译segments
        from ..text_translator import TextTranslator
        text_translator = TextTranslator(self.config)
        
        # 获取全局进度回调
        progress_callback = getattr(self.context, 'progress_callback', None)
        
        translation_result = text_translator.translate_segments_with_output_manager(
            segments, 
            self.output_manager,
            progress_callback
        )
        
        if not translation_result.get("success"):
            return {
                "success": False,
                "error": translation_result.get("error", "文本翻译失败")
            }
        
        translated_segments = translation_result.get("translated_segments", [])
        self.logger.info(f'翻译完成: {len(translated_segments)} 个片段')
        
        # 保存翻译后的segments供步骤6使用
        translated_segments_file = os.path.join(self.task_dir, "05_translated_segments.json")
        self.write_json(os.path.basename(translated_segments_file), translated_segments)
        
        self.output_manager.log(f"步骤5完成: 翻译完成，{len(translated_segments)} 个片段")
        
        return {
            "success": True,
            "translated_segments": translated_segments,
            "translated_segments_file": "05_translated_segments.json"
        }

