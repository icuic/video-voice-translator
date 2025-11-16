"""
输出文件管理器

负责管理视频翻译系统的所有输出文件，包括：
- 按任务创建独立目录
- 统一的文件命名规范
- 日志记录管理
- Web UI日志保存
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

# 导出步骤编号常量供其他模块使用
__all__ = ['StepNumbers', 'FileNames', 'OutputManager']

try:
    import yaml
except ImportError:
    yaml = None


class StepNumbers:
    """步骤编号常量（类似C语言的宏定义）
    
    统一管理所有步骤编号，修改时只需改一处即可全局生效。
    """
    # 步骤1: 音频提取
    STEP_1 = 1
    
    # 步骤2: 音频分离
    STEP_2 = 2
    
    # 步骤3: 多说话人处理
    STEP_3 = 3
    
    # 步骤4: 语音识别
    STEP_4 = 4
    
    # 步骤5: 文本翻译
    STEP_5 = 5
    
    # 步骤6: 参考音频提取
    STEP_6 = 6
    
    # 步骤7: 音色克隆
    STEP_7 = 7
    
    # 步骤8: 音频合并
    STEP_8 = 8
    
    # 步骤9: 视频合成
    STEP_9 = 9


class FileNames:
    """文件命名规范常量"""
    
    # 步骤1: 音频提取
    STEP1_AUDIO = "01_audio.wav"
    
    # 步骤2: 音频分离
    STEP2_VOCALS = "02_vocals.wav"
    STEP2_ACCOMPANIMENT = "02_accompaniment.wav"
    
    # 步骤3: 多说话人处理（输出在spk_*/目录，不在此定义）
    
    # 步骤4: 语音识别
    STEP4_WHISPER_RAW = "04_whisper_raw.json"
    STEP4_WHISPER_RAW_SEGMENTS = "04_whisper_raw_segments.txt"
    STEP4_WHISPER_RAW_TRANSCRIPTION = "04_whisper_raw_transcription.txt"
    STEP4_WHISPER_RAW_WORD_TIMESTAMPS = "04_whisper_raw_word_timestamps.txt"
    STEP4_SEGMENTS_TXT = "04_segments.txt"
    STEP4_SEGMENTS_JSON = "04_segments.json"
    
    # 步骤5: 文本翻译
    STEP5_TRANSLATION = "05_translation.txt"
    STEP5_LLM_INTERACTION = "05_llm_interaction.txt"
    
    # 步骤6: 参考音频提取
    STEP6_REF_SEGMENT_PREFIX = "06_ref_segment_"
    
    # 步骤7: 音色克隆
    STEP7_SEGMENT_PREFIX = "07_segment_"
    
    # 音频文件夹
    REF_AUDIO_FOLDER = "ref_audio"      # 分段人声音频文件夹
    CLONED_AUDIO_FOLDER = "cloned_audio"  # 克隆得到的分段音频文件夹
    
    # 步骤8: 音频合并
    STEP8_FINAL_VOICE = "08_final_voice.wav"
    
    # 步骤9: 视频输出
    STEP9_FINAL_VIDEO = "09_translated.mp4"
    
    # 日志文件
    PROCESSING_LOG = "processing_log.txt"
    WEBUI_LOG = "webui_log.txt"
    
    # 性能统计文件
    PERFORMANCE_STATS_JSON = "translation_stats.json"
    PERFORMANCE_STATS_CSV = "translation_stats.csv"


class OutputManager:
    """输出文件管理器"""
    
    def __init__(self, input_file: str, base_output_dir: str = "data/outputs", config_path: str = "config.yaml"):
        """
        初始化输出管理器
        
        Args:
            input_file: 输入文件路径
            base_output_dir: 基础输出目录
            config_path: 配置文件路径
        """
        self.input_file = input_file
        self.base_output_dir = base_output_dir
        self.config_path = config_path
        
        # 加载配置
        self.config = self._load_config()
        
        # 生成任务目录名
        self.task_dir_name = self._generate_task_dir_name()
        self.task_dir = None
        self.webui_log_path = None
        
        # 初始化日志记录器
        self.logger = self._setup_logger()
        
        # 初始化性能统计
        from .performance_stats import PerformanceStats
        self.performance_stats = PerformanceStats(
            video_info={"filename": os.path.basename(input_file)},
            config=self.config
        )
        
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if yaml is None:
                print("警告: PyYAML未安装，使用默认配置")
                return {}
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"警告: 无法加载配置文件 {self.config_path}: {e}")
            return {}
    
    def _generate_task_dir_name(self) -> str:
        """生成任务目录名 (时间戳_文件名)"""
        # 获取当前时间戳
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # 获取输入文件名（不含扩展名）
        input_name = Path(self.input_file).stem
        
        # 生成任务目录名
        return f"{timestamp}_{input_name}"
    
    def _extract_task_info(self) -> Optional[Tuple[str, str]]:
        """
        从任务目录名中提取任务名和时间戳
        
        任务目录名格式: 2025-11-12_01-01-44_西游记之女儿国片段
        - 时间戳: 2025-11-12_01-01-44 (前两部分，用下划线连接)
        - 任务名: 西游记之女儿国片段 (第3部分及之后)
        
        Returns:
            Optional[Tuple[str, str]]: (任务名, 时间戳)，如果无法解析则返回 None
        """
        if not self.task_dir_name:
            return None
        
        # 按单个下划线分割
        parts = self.task_dir_name.split('_')
        
        # 至少需要3部分：日期、时间、任务名
        if len(parts) < 3:
            return None
        
        try:
            # 前两部分组成时间戳: YYYY-MM-DD_HH-MM-SS
            timestamp = f"{parts[0]}_{parts[1]}"
            
            # 验证时间戳格式
            datetime.strptime(timestamp, "%Y-%m-%d_%H-%M-%S")
            
            # 第3部分及之后组成任务名
            task_name = '_'.join(parts[2:])
            
            # 清理任务名中的非法文件名字符
            task_name = self._sanitize_filename(task_name)
            
            return (task_name, timestamp)
        except (ValueError, IndexError):
            # 如果无法解析，返回 None
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        清理文件名，移除或替换非法字符
        
        Args:
            filename: 原始文件名
            
        Returns:
            str: 清理后的文件名
        """
        # Windows/Linux 文件系统不允许的字符
        illegal_chars = '<>:"/\\|?*'
        sanitized = filename
        for char in illegal_chars:
            sanitized = sanitized.replace(char, '_')
        
        # 移除首尾空格和点
        sanitized = sanitized.strip(' .')
        
        # 如果为空，使用默认名称
        if not sanitized:
            sanitized = "translated"
        
        return sanitized
    
    def create_task_directory(self) -> str:
        """
        创建任务专属目录
        
        Returns:
            str: 任务目录的完整路径
        """
        # 创建任务目录
        self.task_dir = os.path.join(self.base_output_dir, self.task_dir_name)
        os.makedirs(self.task_dir, exist_ok=True)
        
        # 创建音频子文件夹
        self._create_audio_folders()
        
        # 记录日志
        self.logger.info(f"创建任务目录: {self.task_dir}")
        
        return self.task_dir
    
    def _create_audio_folders(self):
        """创建音频相关的子文件夹"""
        if not self.task_dir:
            return
        
        # 创建分段人声音频文件夹
        ref_audio_dir = os.path.join(self.task_dir, FileNames.REF_AUDIO_FOLDER)
        os.makedirs(ref_audio_dir, exist_ok=True)
        
        # 创建克隆音频文件夹
        cloned_audio_dir = os.path.join(self.task_dir, FileNames.CLONED_AUDIO_FOLDER)
        os.makedirs(cloned_audio_dir, exist_ok=True)
        
        self.logger.info(f"创建音频子文件夹: {ref_audio_dir}, {cloned_audio_dir}")
    
    def get_file_path(self, step: int, file_type: str) -> str:
        """
        获取指定步骤的文件路径
        
        Args:
            step: 处理步骤 (1-9)
            file_type: 文件类型
            
        Returns:
            str: 文件完整路径
        """
        if not self.task_dir:
            raise RuntimeError("任务目录未创建，请先调用 create_task_directory()")
        
        # 根据步骤和文件类型生成文件名
        filename = self._get_filename(step, file_type)
        return os.path.join(self.task_dir, filename)
    
    def get_segment_path(self, segment_index: int) -> str:
        """
        获取音频片段路径 (cloned_audio/07_segment_XXX.wav)
        
        Args:
            segment_index: 片段索引
            
        Returns:
            str: 片段文件完整路径
        """
        if not self.task_dir:
            raise RuntimeError("任务目录未创建，请先调用 create_task_directory()")
        
        filename = f"{FileNames.STEP7_SEGMENT_PREFIX}{segment_index:03d}.wav"
        return os.path.join(self.task_dir, FileNames.CLONED_AUDIO_FOLDER, filename)
    
    def get_ref_audio_folder(self) -> str:
        """
        获取参考音频文件夹路径
        
        Returns:
            str: 参考音频文件夹路径
        """
        if not self.task_dir:
            raise RuntimeError("任务目录未创建，请先调用 create_task_directory()")
        
        return os.path.join(self.task_dir, FileNames.REF_AUDIO_FOLDER)
    
    def get_cloned_audio_folder(self) -> str:
        """
        获取克隆音频文件夹路径
        
        Returns:
            str: 克隆音频文件夹路径
        """
        if not self.task_dir:
            raise RuntimeError("任务目录未创建，请先调用 create_task_directory()")
        
        return os.path.join(self.task_dir, FileNames.CLONED_AUDIO_FOLDER)
    
    def get_ref_segment_path(self, segment_index: int) -> str:
        """
        获取参考音频片段路径 (ref_audio/06_ref_segment_XXX.wav)
        
        Args:
            segment_index: 片段索引
            
        Returns:
            str: 参考音频片段文件完整路径
        """
        if not self.task_dir:
            raise RuntimeError("任务目录未创建，请先调用 create_task_directory()")
        
        filename = f"{FileNames.STEP6_REF_SEGMENT_PREFIX}{segment_index:03d}.wav"
        return os.path.join(self.task_dir, FileNames.REF_AUDIO_FOLDER, filename)
    
    def get_cloned_segment_path(self, segment_index: int) -> str:
        """
        获取克隆音频片段路径 (cloned_audio/07_segment_XXX.wav)
        
        Args:
            segment_index: 片段索引
            
        Returns:
            str: 克隆音频片段文件完整路径
        """
        if not self.task_dir:
            raise RuntimeError("任务目录未创建，请先调用 create_task_directory()")
        
        filename = f"{FileNames.STEP7_SEGMENT_PREFIX}{segment_index:03d}.wav"
        return os.path.join(self.task_dir, FileNames.CLONED_AUDIO_FOLDER, filename)
    
    def _get_filename(self, step: int, file_type: str) -> str:
        """根据步骤和文件类型获取文件名"""
        # 特殊处理步骤9的最终视频/音频文件
        if step == StepNumbers.STEP_9 and file_type == "final_video":
            # 尝试提取任务名和时间戳
            task_info = self._extract_task_info()
            if task_info:
                task_name, timestamp = task_info
                # 从完整时间戳中提取时分秒部分（格式：YYYY-MM-DD_HH-MM-SS -> HH_MM_SS）
                time_only = timestamp.split('_')[1] if '_' in timestamp else timestamp
                # 将时分秒中的连字符替换为下划线，统一使用下划线分隔
                time_only = time_only.replace('-', '_')
                # 获取原始文件名以确定扩展名
                base_filename = FileNames.STEP9_FINAL_VIDEO
                # 默认扩展名为 .mp4，但可能被替换为 .wav 或其他格式
                ext = os.path.splitext(base_filename)[1] or ".mp4"
                return f"09_translated_{task_name}_{time_only}{ext}"
            else:
                # 如果无法解析，使用原格式
                return FileNames.STEP9_FINAL_VIDEO
        
        filename_map = {
            (StepNumbers.STEP_1, "audio"): FileNames.STEP1_AUDIO,
            (StepNumbers.STEP_2, "vocals"): FileNames.STEP2_VOCALS,
            (StepNumbers.STEP_2, "accompaniment"): FileNames.STEP2_ACCOMPANIMENT,
            (StepNumbers.STEP_4, "whisper_raw"): FileNames.STEP4_WHISPER_RAW,
            (StepNumbers.STEP_4, "whisper_raw_segments"): FileNames.STEP4_WHISPER_RAW_SEGMENTS,
            (StepNumbers.STEP_4, "whisper_raw_transcription"): FileNames.STEP4_WHISPER_RAW_TRANSCRIPTION,
            (StepNumbers.STEP_4, "whisper_raw_word_timestamps"): FileNames.STEP4_WHISPER_RAW_WORD_TIMESTAMPS,
            (StepNumbers.STEP_4, "segments_txt"): FileNames.STEP4_SEGMENTS_TXT,
            (StepNumbers.STEP_4, "segments_json"): FileNames.STEP4_SEGMENTS_JSON,
            (StepNumbers.STEP_5, "translation"): FileNames.STEP5_TRANSLATION,
            (StepNumbers.STEP_5, "llm_interaction"): FileNames.STEP5_LLM_INTERACTION,
            (StepNumbers.STEP_8, "final_voice"): FileNames.STEP8_FINAL_VOICE,
            (StepNumbers.STEP_9, "final_video"): FileNames.STEP9_FINAL_VIDEO,
        }
        
        # 处理重试文件类型
        if file_type.startswith("llm_interaction_retry"):
            return f"05_llm_interaction_{file_type.replace('llm_interaction_', '')}.txt"
        
        key = (step, file_type)
        if key in filename_map:
            return filename_map[key]
        else:
            raise ValueError(f"不支持的步骤和文件类型组合: step={step}, file_type={file_type}")
    
    def setup_webui_logging(self):
        """设置Web UI会话日志保存到全局logs目录"""
        # 从配置读取日志目录，如果没有则使用默认值
        log_dir = self.config.get("logging", {}).get("log_dir", "data/logs")
        # 如果是相对路径，基于项目根目录解析
        if not os.path.isabs(log_dir):
            # 获取项目根目录（config.yaml所在目录）
            project_root = os.path.dirname(os.path.abspath(self.config_path))
            webui_logs_dir = os.path.join(project_root, log_dir)
        else:
            webui_logs_dir = log_dir
        os.makedirs(webui_logs_dir, exist_ok=True)
        
        # 生成Web UI会话日志文件名（按日期时间）
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        webui_log_filename = f"webui_{timestamp}.log"
        self.webui_log_path = os.path.join(webui_logs_dir, webui_log_filename)
        
        # 配置日志处理器
        webui_handler = logging.FileHandler(self.webui_log_path, encoding='utf-8')
        webui_handler.setLevel(logging.INFO)
        
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        webui_handler.setFormatter(formatter)
        
        # 添加到根日志器
        root_logger = logging.getLogger()
        root_logger.addHandler(webui_handler)
        
        self.logger.info(f"Web UI会话日志将保存到: {self.webui_log_path}")
        
        return self.webui_log_path
    
    def setup_task_logging(self):
        """设置任务级日志保存到任务目录"""
        if not self.task_dir:
            raise RuntimeError("任务目录未创建，请先调用 create_task_directory()")
        
        # 生成任务日志文件名
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        task_log_filename = f"task_{timestamp}.log"
        self.task_log_path = os.path.join(self.task_dir, task_log_filename)
        
        # 配置任务日志处理器
        task_handler = logging.FileHandler(self.task_log_path, encoding='utf-8')
        task_handler.setLevel(logging.INFO)
        
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        task_handler.setFormatter(formatter)
        
        # 添加到根日志器
        root_logger = logging.getLogger()
        root_logger.addHandler(task_handler)
        
        self.logger.info(f"任务日志将保存到: {self.task_log_path}")
        
        return self.task_log_path
    
    def log(self, message: str):
        """
        记录到 processing_log.txt
        
        Args:
            message: 日志消息
        """
        if not self.task_dir:
            raise RuntimeError("任务目录未创建，请先调用 create_task_directory()")
        
        # 记录到处理日志
        log_file = os.path.join(self.task_dir, FileNames.PROCESSING_LOG)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{timestamp} - {message}\n")
        
        # 同时记录到标准日志
        self.logger.info(message)
    
    def save_processing_log(self, log_content: str):
        """
        保存处理日志内容
        
        Args:
            log_content: 日志内容
        """
        if not self.task_dir:
            raise RuntimeError("任务目录未创建，请先调用 create_task_directory()")
        
        log_file = os.path.join(self.task_dir, FileNames.PROCESSING_LOG)
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(log_content)
        
        self.logger.info(f"处理日志已保存到: {log_file}")
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger(f"OutputManager_{self.task_dir_name}")
        logger.setLevel(logging.INFO)
        
        # 避免重复添加处理器
        if not logger.handlers:
            # 控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # 设置格式
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            
            logger.addHandler(console_handler)
        
        return logger
    
    def get_task_info(self) -> Dict[str, str]:
        """
        获取任务信息
        
        Returns:
            Dict[str, str]: 任务信息字典
        """
        return {
            "input_file": self.input_file,
            "task_dir_name": self.task_dir_name,
            "task_dir": self.task_dir,
            "base_output_dir": self.base_output_dir,
            "webui_log_path": self.webui_log_path
        }
    
    def cleanup_old_tasks(self, keep_days: int = 7, keep_count: int = 10):
        """
        清理旧的任务目录
        
        Args:
            keep_days: 保留天数
            keep_count: 保留数量
        """
        if not os.path.exists(self.base_output_dir):
            return
        
        # 获取所有任务目录
        task_dirs = []
        for item in os.listdir(self.base_output_dir):
            item_path = os.path.join(self.base_output_dir, item)
            if os.path.isdir(item_path):
                # 检查目录名格式 (时间戳_文件名)
                if len(item.split('_')) >= 4:  # YYYY-MM-DD_HH-MM-SS_文件名
                    task_dirs.append(item_path)
        
        # 按修改时间排序
        task_dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # 删除旧目录
        deleted_count = 0
        for i, task_dir in enumerate(task_dirs):
            if i >= keep_count:  # 保留最新的几个
                try:
                    import shutil
                    shutil.rmtree(task_dir)
                    deleted_count += 1
                    self.logger.info(f"删除旧任务目录: {task_dir}")
                except Exception as e:
                    self.logger.error(f"删除目录失败 {task_dir}: {e}")
        
        self.logger.info(f"清理完成，删除了 {deleted_count} 个旧任务目录")
    
    def get_performance_stats(self) -> 'PerformanceStats':
        """获取性能统计对象"""
        return self.performance_stats
    
    def save_performance_stats(self) -> None:
        """保存性能统计数据"""
        if self.task_dir:
            # 保存任务级统计
            json_path = os.path.join(self.task_dir, FileNames.PERFORMANCE_STATS_JSON)
            csv_path = os.path.join(self.task_dir, FileNames.PERFORMANCE_STATS_CSV)
            
            self.performance_stats.save_to_json(json_path)
            self.performance_stats.save_to_csv(csv_path)
            
            # 追加到全局统计
            self.performance_stats.append_to_global_stats()
            
            self.logger.info(f"性能统计已保存: {json_path}")
        else:
            self.logger.warning("任务目录未创建，无法保存性能统计")


# 便捷函数
def create_output_manager(input_file: str, base_output_dir: str = "data/outputs", config_path: str = "config.yaml") -> OutputManager:
    """
    创建输出管理器的便捷函数
    
    Args:
        input_file: 输入文件路径
        base_output_dir: 基础输出目录
        config_path: 配置文件路径
        
    Returns:
        OutputManager: 输出管理器实例
    """
    return OutputManager(input_file, base_output_dir, config_path)
