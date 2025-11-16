"""
媒体输出模块
将中文配音与原始视频合成，生成最终的配音视频
"""

from .video_output_generator import VideoOutputGenerator as _Base


class MediaOutputGenerator(_Base):
    """媒体输出生成器（兼容原视频输出生成器的实现）"""
    pass


