"""
步骤9: 视频合成
视频合成
"""

import os
import subprocess
import shutil
from typing import Dict, Any
from ..output_manager import OutputManager, StepNumbers
from .base_step import BaseStep
from .processing_context import ProcessingContext


class Step9VideoSynthesis(BaseStep):
    """步骤9: 视频合成"""
    
    def execute(self) -> Dict[str, Any]:
        """执行步骤9: 视频合成"""
        
        # 读取最终音频文件
        final_audio_path = self.output_manager.get_file_path(StepNumbers.STEP_8, "final_voice")
        if not os.path.exists(final_audio_path):
            return {
                "success": False,
                "error": f"最终音频文件不存在: {final_audio_path}"
            }
        
        # 读取元数据
        metadata = self.context.load_metadata()
        
        # 读取原始输入文件
        original_file = os.path.join(self.task_dir, "00_original_input.*")
        # 查找原始文件（可能扩展名不同）
        original_input_path = None
        for ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg']:
            test_path = os.path.join(self.task_dir, f"00_original_input{ext}")
            if os.path.exists(test_path):
                original_input_path = test_path
                break
        
        if not original_input_path:
            return {
                "success": False,
                "error": "原始输入文件不存在"
            }
        
        # 使用OutputManager生成最终输出路径
        final_video_path = self.output_manager.get_file_path(StepNumbers.STEP_9, "final_video")
        
        if self.context.is_video:
            # 视频文件：合并原始视频、中文配音和背景音乐
            self.logger.info("合并视频、中文配音和背景音乐...")
            
            # 检查是否存在背景音乐文件
            accompaniment_path = self.output_manager.get_file_path(StepNumbers.STEP_2, "accompaniment")
            if os.path.exists(accompaniment_path):
                # 三个输入：原始视频、中文配音、背景音乐
                # 先降低背景音乐音量到30%，然后混合配音和背景音乐
                cmd = [
                    'ffmpeg',
                    '-i', original_input_path,        # 原始视频
                    '-i', final_audio_path,            # 中文配音
                    '-i', accompaniment_path,          # 背景音乐
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-filter_complex', '[2:a]volume=0.3[accompaniment_low];[1:a][accompaniment_low]amix=inputs=2:duration=first[aout]',  # 降低背景音乐音量后混合
                    '-map', '0:v:0',                  # 使用原始视频
                    '-map', '[aout]',                  # 使用混合后的音频
                    '-y',
                    final_video_path
                ]
                self.logger.info(f'使用背景音乐（已降低到30%音量）: {accompaniment_path}')
            else:
                # 只有两个输入：原始视频、中文配音
                cmd = [
                    'ffmpeg',
                    '-i', original_input_path,
                    '-i', final_audio_path,
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                    '-y',
                    final_video_path
                ]
                self.logger.warning('未找到背景音乐文件，仅使用中文配音')
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"视频创建失败: {result.stderr}"
                }
            
            self.logger.info(f'最终翻译视频创建成功: {final_video_path}')
            self.output_manager.log(f"步骤9完成: 最终翻译视频创建成功: {final_video_path}")
            
        else:
            # 音频文件：只输出中文配音音频
            self.logger.info("输出中文配音音频...")
            # 替换扩展名为 .wav（步骤8输出的就是.wav格式），保持新命名格式（如果已应用）
            base_name = os.path.splitext(final_video_path)[0]
            final_video_path = f"{base_name}.wav"
            shutil.copy2(final_audio_path, final_video_path)
            
            self.logger.info(f'中文配音音频已保存: {final_video_path}')
            self.output_manager.log(f"步骤9完成: 中文配音音频已保存: {final_video_path}")
        
        return {
            "success": True,
            "final_video_path": final_video_path,
            "is_video": self.context.is_video
        }

