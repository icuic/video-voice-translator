"""
音频提取器模块
从视频文件中提取音频，或处理音频文件
"""

import os
import logging
import ffmpeg
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from .utils import validate_file_path, create_output_dir, safe_filename


class AudioExtractor:
    """音频提取器类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化音频提取器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 音频处理参数
        self.audio_config = config.get("audio", {})
        self.sample_rate = self.audio_config.get("sample_rate", 16000)
        self.format = self.audio_config.get("format", "wav")
        self.channels = self.audio_config.get("channels", 1)
        self.bit_depth = self.audio_config.get("bit_depth", 16)
    
    def extract(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """
        从输入文件提取音频
        
        Args:
            input_path: 输入文件路径（视频或音频）
            output_path: 输出音频文件路径
            
        Returns:
            提取结果字典
        """
        if not validate_file_path(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")
        
        self.logger.info(f"开始音频提取: {input_path} -> {output_path}")
        
        # 创建输出目录
        create_output_dir(os.path.dirname(output_path))
        
        # 检查输入文件类型
        input_ext = Path(input_path).suffix.lower().lstrip('.')
        
        try:
            if self._is_audio_file(input_ext):
                # 如果是音频文件，直接转换格式
                result = self._convert_audio(input_path, output_path)
            else:
                # 如果是视频文件，提取音频
                result = self._extract_audio_from_video(input_path, output_path)
            
            self.logger.info("音频提取完成")
            return result
            
        except Exception as e:
            self.logger.error(f"音频提取失败: {e}")
            raise
    
    def _is_audio_file(self, file_ext: str) -> bool:
        """判断是否为音频文件"""
        audio_formats = ["mp3", "wav", "flac", "aac", "ogg", "m4a"]
        return file_ext in audio_formats
    
    def _extract_audio_from_video(self, video_path: str, output_path: str) -> Dict[str, Any]:
        """
        从视频文件提取音频
        
        Args:
            video_path: 视频文件路径
            output_path: 输出音频文件路径
            
        Returns:
            提取结果字典
        """
        try:
            # 构建FFmpeg命令
            input_stream = ffmpeg.input(video_path)
            
            # 音频处理参数
            audio_stream = input_stream.audio
            
            # 设置输出参数
            output_stream = ffmpeg.output(
                audio_stream,
                output_path,
                acodec='pcm_s16le',  # 16位PCM编码
                ar=self.sample_rate,  # 采样率
                ac=self.channels,     # 声道数
                f=self.format         # 输出格式
            )
            
            # 执行转换
            ffmpeg.run(output_stream, overwrite_output=True, quiet=True)
            
            # 获取输出文件信息
            output_size = os.path.getsize(output_path)
            
            return {
                "success": True,
                "input_path": video_path,
                "output_path": output_path,
                "output_size": output_size,
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "format": self.format,
                "extraction_type": "video_to_audio"
            }
            
        except ffmpeg.Error as e:
            self.logger.error(f"FFmpeg错误: {e}")
            raise RuntimeError(f"音频提取失败: {e}")
    
    def _convert_audio(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """
        转换音频文件格式
        
        Args:
            input_path: 输入音频文件路径
            output_path: 输出音频文件路径
            
        Returns:
            转换结果字典
        """
        try:
            # 如果输入和输出格式相同，直接复制
            input_ext = Path(input_path).suffix.lower().lstrip('.')
            output_ext = Path(output_path).suffix.lower().lstrip('.')
            
            if input_ext == output_ext and self._is_same_format(input_path, output_path):
                shutil.copy2(input_path, output_path)
                extraction_type = "audio_copy"
            else:
                # 使用FFmpeg转换格式
                input_stream = ffmpeg.input(input_path)
                audio_stream = input_stream.audio
                
                output_stream = ffmpeg.output(
                    audio_stream,
                    output_path,
                    acodec='pcm_s16le',
                    ar=self.sample_rate,
                    ac=self.channels,
                    f=self.format
                )
                
                ffmpeg.run(output_stream, overwrite_output=True, quiet=True)
                extraction_type = "audio_convert"
            
            # 获取输出文件信息
            output_size = os.path.getsize(output_path)
            
            return {
                "success": True,
                "input_path": input_path,
                "output_path": output_path,
                "output_size": output_size,
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "format": self.format,
                "extraction_type": extraction_type
            }
            
        except ffmpeg.Error as e:
            self.logger.error(f"FFmpeg转换错误: {e}")
            raise RuntimeError(f"音频转换失败: {e}")
    
    def _is_same_format(self, input_path: str, output_path: str) -> bool:
        """
        检查输入和输出是否为相同格式和参数
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            
        Returns:
            是否为相同格式
        """
        try:
            # 获取输入文件信息
            probe = ffmpeg.probe(input_path)
            audio_stream = None
            
            for stream in probe['streams']:
                if stream['codec_type'] == 'audio':
                    audio_stream = stream
                    break
            
            if not audio_stream:
                return False
            
            # 检查参数是否匹配
            input_sample_rate = int(audio_stream.get('sample_rate', 0))
            input_channels = int(audio_stream.get('channels', 0))
            input_codec = audio_stream.get('codec_name', '')
            
            # 检查是否匹配目标参数
            return (input_sample_rate == self.sample_rate and
                    input_channels == self.channels and
                    input_codec == 'pcm_s16le')
            
        except Exception:
            return False
    
    def extract_with_progress(self, input_path: str, output_path: str, 
                            progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        带进度回调的音频提取
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            progress_callback: 进度回调函数
            
        Returns:
            提取结果字典
        """
        # 获取输入文件时长
        try:
            probe = ffmpeg.probe(input_path)
            duration = float(probe['format']['duration'])
        except Exception:
            duration = 0
        
        # 执行提取
        result = self.extract(input_path, output_path)
        
        # 调用进度回调
        if progress_callback:
            progress_callback(100.0, "音频提取完成")
        
        return result



