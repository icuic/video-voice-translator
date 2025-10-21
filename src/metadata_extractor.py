"""
元数据提取器模块
使用FFmpeg和OpenCV提取视频和音频的元数据信息
"""

import os
import logging
import cv2
import ffmpeg
from typing import Dict, Any, Optional
from .utils import validate_file_path, get_file_info


class MetadataExtractor:
    """元数据提取器类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def extract(self, file_path: str) -> Dict[str, Any]:
        """
        提取文件元数据
        
        Args:
            file_path: 文件路径
            
        Returns:
            元数据字典
        """
        if not validate_file_path(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        self.logger.info(f"开始提取元数据: {file_path}")
        
        # 获取文件基本信息
        file_info = get_file_info(file_path)
        file_ext = file_info["extension"]
        
        metadata = {
            "file_info": file_info,
            "is_video": self._is_video_file(file_ext),
            "is_audio": self._is_audio_file(file_ext)
        }
        
        try:
            if metadata["is_video"]:
                # 提取视频元数据
                video_metadata = self._extract_video_metadata(file_path)
                metadata.update(video_metadata)
            elif metadata["is_audio"]:
                # 提取音频元数据
                audio_metadata = self._extract_audio_metadata(file_path)
                metadata.update(audio_metadata)
            else:
                raise ValueError(f"不支持的文件格式: {file_ext}")
                
        except Exception as e:
            self.logger.error(f"元数据提取失败: {e}")
            raise
        
        self.logger.info("元数据提取完成")
        return metadata
    
    def _is_video_file(self, file_ext: str) -> bool:
        """判断是否为视频文件"""
        video_formats = ["mp4", "avi", "mov", "mkv", "wmv", "flv", "webm"]
        return file_ext in video_formats
    
    def _is_audio_file(self, file_ext: str) -> bool:
        """判断是否为音频文件"""
        audio_formats = ["mp3", "wav", "flac", "aac", "ogg", "m4a"]
        return file_ext in audio_formats
    
    def _extract_video_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        提取视频元数据
        
        Args:
            file_path: 视频文件路径
            
        Returns:
            视频元数据字典
        """
        metadata = {}
        
        try:
            # 使用FFmpeg提取详细信息
            probe = ffmpeg.probe(file_path)
            
            # 查找视频流
            video_stream = None
            audio_stream = None
            
            for stream in probe['streams']:
                if stream['codec_type'] == 'video' and video_stream is None:
                    video_stream = stream
                elif stream['codec_type'] == 'audio' and audio_stream is None:
                    audio_stream = stream
            
            # 视频信息
            if video_stream:
                metadata.update({
                    "video": {
                        "width": int(video_stream.get('width', 0)),
                        "height": int(video_stream.get('height', 0)),
                        "fps": self._parse_fps(video_stream.get('r_frame_rate', '0/1')),
                        "duration": float(video_stream.get('duration', 0)),
                        "codec": video_stream.get('codec_name', 'unknown'),
                        "bitrate": int(video_stream.get('bit_rate', 0)) if video_stream.get('bit_rate') else None
                    }
                })
            
            # 音频信息
            if audio_stream:
                metadata.update({
                    "audio": {
                        "sample_rate": int(audio_stream.get('sample_rate', 0)),
                        "channels": int(audio_stream.get('channels', 0)),
                        "duration": float(audio_stream.get('duration', 0)),
                        "codec": audio_stream.get('codec_name', 'unknown'),
                        "bitrate": int(audio_stream.get('bit_rate', 0)) if audio_stream.get('bit_rate') else None
                    }
                })
            
            # 使用OpenCV获取额外信息
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                metadata["video"]["frame_count"] = frame_count
                cap.release()
            
            # 格式信息
            format_info = probe.get('format', {})
            metadata["format"] = {
                "name": format_info.get('format_name', 'unknown'),
                "duration": float(format_info.get('duration', 0)),
                "size": int(format_info.get('size', 0)),
                "bitrate": int(format_info.get('bit_rate', 0)) if format_info.get('bit_rate') else None
            }
            
        except Exception as e:
            self.logger.error(f"FFmpeg元数据提取失败: {e}")
            # 尝试使用OpenCV作为备用方案
            metadata = self._extract_video_metadata_opencv(file_path)
        
        return metadata
    
    def _extract_audio_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        提取音频元数据
        
        Args:
            file_path: 音频文件路径
            
        Returns:
            音频元数据字典
        """
        metadata = {}
        
        try:
            # 使用FFmpeg提取音频信息
            probe = ffmpeg.probe(file_path)
            
            # 查找音频流
            audio_stream = None
            for stream in probe['streams']:
                if stream['codec_type'] == 'audio':
                    audio_stream = stream
                    break
            
            if audio_stream:
                metadata["audio"] = {
                    "sample_rate": int(audio_stream.get('sample_rate', 0)),
                    "channels": int(audio_stream.get('channels', 0)),
                    "duration": float(audio_stream.get('duration', 0)),
                    "codec": audio_stream.get('codec_name', 'unknown'),
                    "bitrate": int(audio_stream.get('bit_rate', 0)) if audio_stream.get('bit_rate') else None
                }
            
            # 格式信息
            format_info = probe.get('format', {})
            metadata["format"] = {
                "name": format_info.get('format_name', 'unknown'),
                "duration": float(format_info.get('duration', 0)),
                "size": int(format_info.get('size', 0)),
                "bitrate": int(format_info.get('bit_rate', 0)) if format_info.get('bit_rate') else None
            }
            
        except Exception as e:
            self.logger.error(f"音频元数据提取失败: {e}")
            raise
        
        return metadata
    
    def _extract_video_metadata_opencv(self, file_path: str) -> Dict[str, Any]:
        """
        使用OpenCV提取视频元数据（备用方案）
        
        Args:
            file_path: 视频文件路径
            
        Returns:
            视频元数据字典
        """
        metadata = {}
        
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {file_path}")
        
        try:
            # 基本视频信息
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0
            
            metadata["video"] = {
                "width": width,
                "height": height,
                "fps": fps,
                "frame_count": frame_count,
                "duration": duration,
                "codec": "unknown",
                "bitrate": None
            }
            
            # 音频信息（OpenCV无法直接获取，设为默认值）
            metadata["audio"] = {
                "sample_rate": 0,
                "channels": 0,
                "duration": duration,
                "codec": "unknown",
                "bitrate": None
            }
            
        finally:
            cap.release()
        
        return metadata
    
    def _parse_fps(self, fps_str: str) -> float:
        """
        解析帧率字符串
        
        Args:
            fps_str: 帧率字符串，如 "30/1" 或 "29.97"
            
        Returns:
            帧率数值
        """
        try:
            if '/' in fps_str:
                numerator, denominator = fps_str.split('/')
                return float(numerator) / float(denominator)
            else:
                return float(fps_str)
        except (ValueError, ZeroDivisionError):
            return 0.0



