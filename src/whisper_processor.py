"""
Whisper语音识别处理器模块
使用OpenAI Whisper进行语音识别和转录
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from .utils import validate_file_path, create_output_dir, safe_filename
from .punctuation_segment_optimizer import PunctuationSegmentOptimizer
from .semantic_segmenter import SemanticSegmenter
from .output_manager import OutputManager, StepNumbers
import math

try:
    import soundfile as sf
except Exception:
    sf = None

# 尝试导入原生 Whisper
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

# 尝试导入 Faster-Whisper
try:
    from faster_whisper import WhisperModel as FasterWhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False


class WhisperProcessor:
    """Whisper语音识别处理器类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化Whisper处理器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Whisper配置
        self.whisper_config = config.get("whisper", {})
        self.backend = self.whisper_config.get("backend", "whisper")  # 后端选择: "whisper" 或 "faster-whisper"
        self.model_size = self.whisper_config.get("model_size", "base")
        self.language = self.whisper_config.get("language", "auto")
        self.task = self.whisper_config.get("task", "transcribe")
        self.device = self.whisper_config.get("device", "auto")
        self.fp16 = self.whisper_config.get("fp16", False)  # FP16精度加速配置
        
        # Faster-Whisper 参数配置
        self.faster_whisper_params = self.whisper_config.get("faster_whisper_params", {
            "beam_size": 5,
            "condition_on_previous_text": True,
            "compression_ratio_threshold": 2.4,
            "log_prob_threshold": -1.0,
            "no_speech_threshold": 0.6,
            "vad_filter": True,
            "vad_parameters": {
                "min_silence_duration_ms": 500
            }
        })
        
        # 检查后端可用性
        if self.backend == "faster-whisper" and not FASTER_WHISPER_AVAILABLE:
            if WHISPER_AVAILABLE:
                self.logger.warning("Faster-Whisper 不可用，回退到原生 Whisper")
                self.backend = "whisper"
            else:
                raise ImportError("配置为 faster-whisper，但 faster-whisper 和原生 whisper 都不可用")
        
        if self.backend == "whisper" and not WHISPER_AVAILABLE:
            if FASTER_WHISPER_AVAILABLE:
                self.logger.warning("原生 Whisper 不可用，回退到 Faster-Whisper")
                self.backend = "faster-whisper"
            else:
                raise ImportError("配置为 whisper，但 whisper 和 faster-whisper 都不可用")
        
        # 初始化模型
        try:
            self.logger.info(f"使用后端: {self.backend}")
            self.logger.info(f"加载模型: {self.model_size}")
            self.logger.info(f"FP16精度加速: {'启用' if self.fp16 else '禁用'}")
            
            # 记录 Faster-Whisper 参数（如果使用）
            if self.backend == "faster-whisper":
                self.logger.info(f"Faster-Whisper 参数: beam_size={self.faster_whisper_params.get('beam_size')}, "
                               f"vad_filter={self.faster_whisper_params.get('vad_filter')}, "
                               f"condition_on_previous_text={self.faster_whisper_params.get('condition_on_previous_text')}")
            
            if self.backend == "faster-whisper":
                self._init_faster_whisper()
            else:
                self._init_whisper()
                
            self.logger.info(f"{self.backend} 模型加载成功")
        except Exception as e:
            self.logger.error(f"模型加载失败: {e}")
            raise
        
        # 初始化分段优化器(根据配置选择)
        self.segment_optimizer = None
        segmentation_config = self.whisper_config.get("segmentation", {})
        segmentation_method = segmentation_config.get("method", "semantic")  # 默认使用 semantic

        if segmentation_method == "punctuation":
            try:
                self.segment_optimizer = PunctuationSegmentOptimizer(config)
                self.logger.info("基于标点符号的分段优化器初始化成功")
            except Exception as e:
                self.logger.warning(f"标点符号分段优化器初始化失败: {e}，将使用原始分段")
                self.segment_optimizer = None
        elif segmentation_method != "semantic":
            self.logger.warning(f"不支持的分段方法: {segmentation_method}，将使用原始分段")
        
        # 初始化语义分段器（总是可用）
        try:
            self.semantic_segmenter = SemanticSegmenter(config)
            self.logger.info("语义分段器初始化成功")
        except Exception as e:
            self.logger.warning(f"语义分段器初始化失败: {e}")
            self.semantic_segmenter = None

    def _get_duration_seconds(self, audio_path: str) -> float:
        """返回音频时长（秒），失败则返回0"""
        try:
            if sf is not None:
                f = sf.SoundFile(audio_path)
                return float(len(f)) / float(f.samplerate)
        except Exception:
            pass
        try:
            import librosa
            return float(librosa.get_duration(path=audio_path))
        except Exception:
            return 0.0

    def _should_use_punctuation_prompt(self, detected_language: str, duration_s: float) -> bool:
        """仅对英文且较长录音启用标点引导，避免短句被模板偏置"""
        return (detected_language == "en") and (duration_s >= 8.0)
    
    def _detect_language_and_set_prompt(self, audio_path: str) -> Tuple[Optional[str], Optional[str]]:
        """
        检测语言并设置标点符号引导
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            (detected_language, initial_prompt) 元组
        """
        detected_language = self.language if self.language != "auto" else None
        initial_prompt = None
        duration_s = self._get_duration_seconds(audio_path)
        
        # 如果是中文，使用标点符号引导提示词
        if detected_language == "zh":
            initial_prompt = "这是一段中文语音转录，请使用正确的标点符号，包括句号、逗号、问号等。"
            self.logger.info("检测到中文音频，使用标点符号引导提示词")
        elif detected_language == "en" and self._should_use_punctuation_prompt("en", duration_s):
            initial_prompt = "This is an English sentence with proper punctuation."
            self.logger.info("检测到英文长语音，启用标点引导")
        elif detected_language is None and self.language == "auto":
            # 自动检测语言
            try:
                detection_result = self.detect_language(audio_path)
                detected_language = detection_result.get("detected_language", "en")
                if detected_language == "zh":
                    initial_prompt = "这是一段中文语音转录，请使用正确的标点符号，包括句号、逗号、问号等。"
                    self.logger.info("自动检测到中文音频，使用标点符号引导提示词")
                elif detected_language == "en" and self._should_use_punctuation_prompt("en", duration_s):
                    initial_prompt = "This is an English sentence with proper punctuation."
                    self.logger.info("自动检测到英文且为长语音，启用标点引导")
            except:
                detected_language = "en"
        
        return detected_language, initial_prompt
    
    def _init_whisper(self):
        """初始化原生 Whisper 模型"""
        if not WHISPER_AVAILABLE:
            raise ImportError("原生 Whisper 不可用")
        
        import torch
        
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # 强制使用CUDA设备，设置环境变量避免设备转换问题
        if torch.cuda.is_available():
            self.device = "cuda"
            # 设置环境变量强制使用CUDA
            os.environ["CUDA_VISIBLE_DEVICES"] = "0"
            torch.cuda.set_device(0)
            self.logger.info(f"使用CUDA设备: {torch.cuda.get_device_name(0)}")
            
            # 清理CUDA缓存
            torch.cuda.empty_cache()
        
        # 使用更安全的模型加载方式
        try:
            # 先尝试在CPU上加载，然后移动到CUDA
            if self.device == "cuda":
                try:
                    # 方法1：直接在CUDA上加载
                    self.model = whisper.load_model(self.model_size, device=self.device)
                    self.logger.info(f"Whisper模型成功加载到设备: {self.device}")
                except Exception as cuda_error:
                    # 方法2：先在CPU上加载，然后移动到CUDA
                    self.logger.warning(f"直接CUDA加载失败，尝试CPU加载后移动: {cuda_error}")
                    self.model = whisper.load_model(self.model_size, device="cpu")
                    
                    # 将模型移动到CUDA设备
                    try:
                        self.model = self.model.to(self.device)
                        self.logger.info(f"Whisper模型成功从CPU移动到设备: {self.device}")
                    except Exception as move_error:
                        self.logger.warning(f"模型移动到CUDA失败，回退到CPU: {move_error}")
                        self.device = "cpu"
            else:
                # CPU模式
                self.model = whisper.load_model(self.model_size, device=self.device)
                self.logger.info(f"Whisper模型成功加载到设备: {self.device}")
                
        except Exception as e:
            self.logger.error(f"Whisper模型加载失败: {e}")
            raise
    
    def _init_faster_whisper(self):
        """初始化 Faster-Whisper 模型"""
        import torch

        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        if self.device == "cuda" and torch.cuda.is_available():
            self.device = "cuda"
            os.environ["CUDA_VISIBLE_DEVICES"] = "0"
            torch.cuda.set_device(0)
            self.logger.info(f"使用CUDA设备: {torch.cuda.get_device_name(0)}")
            torch.cuda.empty_cache()
        else:
            self.device = "cpu"
            self.logger.info("使用CPU设备")

        compute_type = "float16" if self.fp16 and self.device == "cuda" else "float32"

        faster_whisper_extra = {}
        cache_dir = self.whisper_config.get("cache_dir")
        if cache_dir:
            faster_whisper_extra["cache_dir"] = cache_dir
        local_files_only_env = os.environ.get("HF_HUB_OFFLINE", "").strip()
        local_files_only_flag = self.whisper_config.get("local_files_only", None)
        if local_files_only_flag is None:
            if local_files_only_env in ("1", "true", "TRUE", "on", "ON"):
                local_files_only_flag = True
            else:
                local_files_only_flag = False
        if local_files_only_flag:
            faster_whisper_extra["local_files_only"] = True

        fallback_to_whisper_reasons = []
        try:
            self.model = FasterWhisperModel(
                self.model_size,
                device=self.device,
                compute_type=compute_type,
                **faster_whisper_extra,
            )
            self.logger.info(
                f"Faster-Whisper模型成功加载到设备: {self.device}, 计算类型: {compute_type}"
            )
            return
        except Exception as faster_err:
            err_name = type(faster_err).__name__
            err_msg = str(faster_err)[:400]
            fallback_to_whisper_reasons.append(
                f"Faster-Whisper init failed: {err_name}: {err_msg}"
            )
            hub_related = any(
                kw in err_msg.lower()
                for kw in (
                    "localentrynotfound",
                    "locate the file on the hub",
                    "filemetadataerror",
                    "connectionerror",
                    "connection timed out",
                    "requests.exceptions",
                    "temporary failure in name resolution",
                    "network is unreachable",
                    "proxyerror",
                    "ssl: cert",
                    "timed out",
                    "httperror",
                )
            ) or err_name in (
                "LocalEntryNotFoundError",
                "FileMetadataError",
                "ConnectionError",
            )
            if not hub_related:
                raise

        if not WHISPER_AVAILABLE:
            msg = (
                f"Faster-Whisper 加载 Systran/faster-whisper-{self.model_size} 失败"
                f"（本地 cache 不存在且 HuggingFace 直连失败），且原生 openai-whisper 未安装，"
                f"无法降级。请在 .env 中配置可用的 HF_ENDPOINT（例如"
                f" HF_ENDPOINT=https://hf-mirror.com），然后手动运行一次："
                f" bash scripts/preload_models.sh  或  pip install openai-whisper 后重试。"
                f" 底层原因: {' | '.join(fallback_to_whisper_reasons)}"
            )
            self.logger.error(msg)
            raise RuntimeError(msg)

        self.logger.warning(
            "Faster-Whisper 加载失败（HuggingFace 不可达或本地无 Systran cache），"
            "自动回退到原生 openai-whisper。"
            " 如需要 faster-whisper 加速，请在 .env 里配置 HF_ENDPOINT=https://hf-mirror.com，"
            "然后执行 bash scripts/preload_models.sh 将 faster-whisper-%s 预下载到本地。"
            " 底层原因: %s",
            self.model_size,
            " | ".join(fallback_to_whisper_reasons),
        )
        self.backend = "whisper"
        self._init_whisper()
    
    def _transcribe_faster_whisper(self, audio_path: str, language: Optional[str] = None, initial_prompt: Optional[str] = None) -> Dict[str, Any]:
        """使用 Faster-Whisper 进行转录"""
        try:
            # 从配置读取 Faster-Whisper 参数
            params = self.faster_whisper_params.copy()
            
            # 基础参数（使用传入的 initial_prompt，如果调用方设置了标点符号引导）
            transcribe_params = {
                "language": language,
                "task": self.task,
                "word_timestamps": True,
                "initial_prompt": initial_prompt,  # 使用传入的参数
            }
            
            # 添加配置的优化参数
            transcribe_params.update({
                "beam_size": params.get("beam_size", 5),
                "condition_on_previous_text": False,
                "compression_ratio_threshold": params.get("compression_ratio_threshold", 2.4),
                "log_prob_threshold": params.get("log_prob_threshold", -1.0),
                "no_speech_threshold": params.get("no_speech_threshold", 0.6),
                "vad_filter": params.get("vad_filter", True),
            })

            # 短音频减小 beam_size，降低语言先验影响
            duration_s = self._get_duration_seconds(audio_path)
            if duration_s > 0 and duration_s <= 5.0:
                transcribe_params["beam_size"] = max(1, min(3, transcribe_params["beam_size"]))
            
            # 添加 VAD 参数（如果启用）
            if transcribe_params["vad_filter"] and "vad_parameters" in params:
                transcribe_params["vad_parameters"] = params["vad_parameters"]
            
            self.logger.info(f"Faster-Whisper 转录参数: beam_size={transcribe_params['beam_size']}, "
                           f"vad_filter={transcribe_params['vad_filter']}, "
                           f"condition_on_previous_text={transcribe_params['condition_on_previous_text']}, "
                           f"initial_prompt={'已设置' if initial_prompt else '未设置'}")
            
            # 执行转录
            segments, info = self.model.transcribe(audio_path, **transcribe_params)
            
            # 将 segments 转换为列表（修复 generator 重复消耗问题）
            segments_list = list(segments)
            self.logger.info(f"🔍 Faster-Whisper 检测到 {len(segments_list)} 个分段")
            
            # 转换 Faster-Whisper 结果格式为 Whisper 兼容格式
            result_text = ""
            result_segments = []
            
            for segment in segments_list:
                segment_text = segment.text.strip()
                result_text += segment_text + " "
                
                # 转换单词时间戳
                words = []
                if hasattr(segment, 'words') and segment.words:
                    for word in segment.words:
                        words.append({
                            "word": word.word,
                            "start": word.start,
                            "end": word.end,
                            "probability": getattr(word, 'probability', 1.0)
                        })
                
                result_segments.append({
                    "id": len(result_segments),
                    "seek": 0,  # Faster-Whisper 不提供 seek
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment_text,
                    "tokens": [],  # Faster-Whisper 不提供 tokens
                    "temperature": 0.0,
                    "avg_logprob": getattr(segment, 'avg_logprob', 0.0),
                    "compression_ratio": getattr(segment, 'compression_ratio', 1.0),
                    "no_speech_prob": getattr(segment, 'no_speech_prob', 0.0),
                    "words": words
                })
            
            # 构建结果字典
            result = {
                "text": result_text.strip(),
                "language": info.language if hasattr(info, 'language') else language or "auto",
                "language_probability": getattr(info, 'language_probability', 1.0),
                "duration": getattr(info, 'duration', 0.0),
                "duration_after_vad": getattr(info, 'duration_after_vad', 0.0),
                "all_language_probs": getattr(info, 'all_language_probs', {}),
                "segments": result_segments
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Faster-Whisper 转录失败: {e}")
            raise
    
    def transcribe_audio(self, audio_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        转录音频文件
        
        Args:
            audio_path: 音频文件路径
            output_dir: 输出目录（可选）
            
        Returns:
            转录结果字典
        """
        if not validate_file_path(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        self.logger.info(f"开始语音识别: {audio_path}")
        
        try:
            # 检测语言并设置标点符号引导
            detected_language, initial_prompt = self._detect_language_and_set_prompt(audio_path)
            
            # 执行转录
            if self.backend == "faster-whisper":
                result = self._transcribe_faster_whisper(audio_path, detected_language, initial_prompt)
            else:
                result = self.model.transcribe(
                audio_path,
                language=detected_language,
                task=self.task,
                verbose=False,
                word_timestamps=True,  # 启用单词时间戳，获得更精确的分段
                initial_prompt=initial_prompt,  # 使用设置的标点符号引导
                # 优化的分段参数
                condition_on_previous_text=False,  # 关闭跨段上下文
                compression_ratio_threshold=1.2,  # 降低阈值，允许更自然的分段
                no_speech_threshold=0.2,  # 降低阈值，保留更多内容
            )
            
            # 处理转录结果
            transcription_result = self._process_transcription_result(result, audio_path, output_dir)
            
            self.logger.info("语音识别完成")
            return transcription_result
            
        except Exception as e:
            self.logger.error(f"语音识别失败: {e}")
            raise
    
    def transcribe_with_output_manager(self, audio_path: str, output_manager: OutputManager) -> Dict[str, Any]:
        """
        使用OutputManager进行语音识别
        
        Args:
            audio_path: 音频文件路径
            output_manager: 输出管理器实例
            
        Returns:
            转录结果字典
        """
        if not validate_file_path(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        self.logger.info(f"开始语音识别: {audio_path}")
        output_manager.log(f"步骤4开始: 语音识别 {audio_path}")
        
        try:
            # 检测语言并设置标点符号引导
            detected_language, initial_prompt = self._detect_language_and_set_prompt(audio_path)
            
            # 执行转录
            if self.backend == "faster-whisper":
                result = self._transcribe_faster_whisper(audio_path, detected_language, initial_prompt)
            else:
                result = self.model.transcribe(
                audio_path,
                language=detected_language,
                task=self.task,
                verbose=False,
                word_timestamps=True,  # 启用单词时间戳，获得更精确的分段
                initial_prompt=initial_prompt,  # 使用设置的标点符号引导
                # 优化的分段参数
                condition_on_previous_text=False,
                compression_ratio_threshold=1.2,  # 降低阈值，允许更自然的分段
                no_speech_threshold=0.2,  # 降低阈值，保留更多内容
            )
            
            # 添加 Whisper 原始分段统计日志
            self.logger.info(f"🔍 Whisper 原始分段数: {len(result.get('segments', []))}")
            for i, seg in enumerate(result.get("segments", [])):
                self.logger.debug(f"  分段 {i+1}: {seg.get('start', 0):.2f}s - {seg.get('end', 0):.2f}s, "
                                 f"文本: '{seg.get('text', '')[:50]}...', "
                                 f"单词数: {len(seg.get('words', []))}")
            
            # 根据配置选择分段优化方式
            segmentation_config = self.whisper_config.get("segmentation", {})
            segmentation_method = segmentation_config.get("method", "semantic")

            if segmentation_method == "punctuation" and self.segment_optimizer is not None:
                # 使用 PunctuationSegmentOptimizer (需要先保存临时文件)
                # 1. 先调用 _process_transcription_result_with_output_manager 保存基础文件
                transcription_result = self._process_transcription_result_with_output_manager(
                    result, audio_path, output_manager
                )
                
                # 2. 获取已保存的文件路径
                transcription_file = output_manager.get_file_path(StepNumbers.STEP_4, "whisper_raw_transcription")
                
                # 3. 调用 PunctuationSegmentOptimizer.optimize_segments
                try:
                    # 从原始 Whisper 结果中提取单词级时间戳
                    raw_word_timestamps = []
                    for segment in result["segments"]:
                        if "words" in segment:
                            raw_word_timestamps.extend(segment["words"])
                    
                    optimized_segments = self.segment_optimizer.optimize_segments(
                        transcription_file, 
                        raw_word_timestamps
                    )
                    
                    # 4. 更新 transcription_result 中的 segments
                    transcription_result["segments"] = optimized_segments
                    
                    # 5. 重新保存优化后的 segments 文件
                    segments_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_txt")
                    segments_json_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
                    
                    # 保存更新后的 segments
                    self._save_optimized_segments(optimized_segments, segments_file, segments_json_file)
                    
                    self.logger.info(f"分段优化完成(punctuation): {len(result['segments'])} -> {len(optimized_segments)} 个片段")
                except Exception as e:
                    self.logger.warning(f"标点符号分段优化失败: {e}，使用原始分段")
            elif segmentation_method == "semantic" and self.semantic_segmenter is not None:
                # 使用新的语义分段器
                self.logger.info("使用语义分段器进行智能分段")
                
                # 1. 收集所有单词时间戳
                all_words = []
                for seg in result.get("segments", []):
                    all_words.extend(seg.get("words", []))
                
                # 2. 使用语义分段器重新分段
                try:
                    semantic_segments = self.semantic_segmenter.segment(all_words, result.get("text", ""))
                    
                    # 3. 更新 result 中的 segments
                    result["segments"] = semantic_segments
                    
                    # 4. 处理转录结果
                    transcription_result = self._process_transcription_result_with_output_manager(
                        result, audio_path, output_manager, apply_optimization=False
                    )
                    
                    self.logger.info(f"语义分段完成: {len(all_words)} 个单词 -> {len(semantic_segments)} 个分段")
                except Exception as e:
                    self.logger.warning(f"语义分段失败: {e}，使用原始分段")
                    transcription_result = self._process_transcription_result_with_output_manager(
                        result, audio_path, output_manager, apply_optimization=False
                    )
            else:
                # 使用原始分段（不支持的分段方法或分段器不可用）
                self.logger.info("使用 Whisper 原始分段（无后处理）")
                transcription_result = self._process_transcription_result_with_output_manager(
                    result, audio_path, output_manager, apply_optimization=False
                )
            
            self.logger.info("语音识别完成")
            output_manager.log("步骤4完成: 语音识别完成")
            return transcription_result
            
        except Exception as e:
            self.logger.error(f"语音识别失败: {e}")
            output_manager.log(f"步骤4失败: {e}")
            raise
    
    def transcribe_with_segments(self, audio_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        带时间段的详细转录
        
        Args:
            audio_path: 音频文件路径
            output_dir: 输出目录（可选）
            
        Returns:
            详细转录结果字典
        """
        if not validate_file_path(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        self.logger.info(f"开始详细语音识别: {audio_path}")
        
        try:
            # 检测语言并设置标点符号引导
            detected_language, initial_prompt = self._detect_language_and_set_prompt(audio_path)
            
            # 执行详细转录，采用优化的分段策略
            if self.backend == "faster-whisper":
                result = self._transcribe_faster_whisper(audio_path, detected_language, initial_prompt)
            else:
                result = self.model.transcribe(
                audio_path,
                language=detected_language,
                task=self.task,
                verbose=False,
                word_timestamps=True,  # 启用单词时间戳，获得更精确的分段
                initial_prompt=initial_prompt,  # 添加标点符号引导
                # 优化的分段参数
                condition_on_previous_text=True,  # 考虑上下文连贯性
                compression_ratio_threshold=1.2,  # 降低阈值，允许更自然的分段
                no_speech_threshold=0.2,  # 降低阈值，保留更多内容
                best_of=1,  # 只生成一个结果
                beam_size=5,  # 使用beam search
                temperature=0.0,  # 确定性输出
                patience=1.0,  # 标准耐心参数
                    fp16=self.fp16  # 🚀 使用配置中的FP16设置
            )
            
            # 保存Whisper原始单词时间戳
            if output_dir:
                self._save_whisper_word_timestamps(result, audio_path, output_dir)
            
            # 处理详细转录结果
            transcription_result = self._process_detailed_transcription_result(result, audio_path, output_dir)
            
            self.logger.info("详细语音识别完成")
            return transcription_result
            
        except Exception as e:
            self.logger.error(f"详细语音识别失败: {e}")
            raise
    
    def transcribe_with_translation(self, audio_path: str, output_dir: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        语音识别、分段优化和翻译的完整流程
        
        Args:
            audio_path: 音频文件路径
            output_dir: 输出目录（可选）
            config: 配置字典（可选）
            
        Returns:
            包含转录、分段和翻译结果的字典
        """
        if not validate_file_path(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        self.logger.info(f"开始语音识别和分段优化: {audio_path}")
        
        try:
            # 检测语言并设置标点符号引导
            detected_language, initial_prompt = self._detect_language_and_set_prompt(audio_path)
            
            # 首先执行转录 - 优化分段参数
            if self.backend == "faster-whisper":
                result = self._transcribe_faster_whisper(audio_path, detected_language, initial_prompt)
            else:
                result = self.model.transcribe(
                audio_path,
                language=detected_language,
                task=self.task,
                verbose=False,
                word_timestamps=True,  # 启用单词时间戳，获得更精确的分段
                initial_prompt=initial_prompt,  # 使用设置的标点符号引导
                # 优化的分段参数
                condition_on_previous_text=False,
                compression_ratio_threshold=1.2,  # 降低阈值，允许更自然的分段
                no_speech_threshold=0.2,  # 降低阈值，保留更多内容
                best_of=1,
                beam_size=3,
                temperature=0.0,
                patience=1.0,
                    fp16=self.fp16  # 🚀 使用配置中的FP16设置
            )
            
            # 保存Whisper原始单词时间戳
            if output_dir:
                self._save_whisper_word_timestamps(result, audio_path, output_dir)
            
            # 提取基础分段信息
            segments = result.get("segments", [])
            whisper_segments = []
            for segment in segments:
                whisper_segments.append({
                    "start": segment.get("start", 0.0),
                    "end": segment.get("end", 0.0),
                    "text": segment.get("text", "").strip(),
                    "words": segment.get("words", [])
                })
            
            # 使用分段优化器（只支持punctuation和semantic）
            segmentation_config = self.whisper_config.get("segmentation", {})
            segmentation_method = segmentation_config.get("method", "semantic")
            
            if segmentation_method == "punctuation" and self.segment_optimizer:
                self.logger.info("开始基于标点符号的分段优化...")
                if output_dir:
                    create_output_dir(output_dir)
                    input_name = Path(audio_path).stem
                    safe_name = safe_filename(input_name)
                    transcription_file = os.path.join(output_dir, f"{safe_name}_transcription.txt")
                    
                    # 先创建转录文件
                    text = " ".join([segment.get("text", "").strip() for segment in whisper_segments])
                    with open(transcription_file, 'w', encoding='utf-8') as f:
                        f.write(text)
                    self.logger.info(f"转录文件已创建: {transcription_file}")
                    
                    # 获取单词时间戳
                    word_timestamps = []
                    for segment in whisper_segments:
                        if "words" in segment:
                            word_timestamps.extend(segment["words"])
                    
                    optimized_segments = self.segment_optimizer.optimize_segments(
                        transcription_file, word_timestamps
                    )
                    
                    # 保存优化结果
                    optimization_file = os.path.join(output_dir, f"{safe_name}_punctuation_segments.json")
                    self.segment_optimizer.save_optimization_result(optimized_segments, optimization_file)
                else:
                    self.logger.warning("输出目录未指定，无法进行标点符号分段，使用原始分段")
                    optimized_segments = whisper_segments
            elif segmentation_method == "semantic" and self.semantic_segmenter:
                self.logger.info("开始语义分段优化...")
                # 收集所有单词时间戳
                all_words = []
                for seg in whisper_segments:
                    all_words.extend(seg.get("words", []))
                
                # 使用语义分段器重新分段
                try:
                    full_text = " ".join([seg.get("text", "").strip() for seg in whisper_segments])
                    optimized_segments = self.semantic_segmenter.segment(all_words, full_text)
                    self.logger.info(f"语义分段完成: {len(all_words)} 个单词 -> {len(optimized_segments)} 个分段")
                except Exception as e:
                    self.logger.warning(f"语义分段失败: {e}，使用原始分段")
                    optimized_segments = whisper_segments
            else:
                self.logger.info("使用 Whisper 原始分段（无分段优化）")
                optimized_segments = whisper_segments
            
            # 清理内存
            import gc
            gc.collect()
            
            # 使用独立的翻译模块进行翻译
            self.logger.info("开始独立翻译...")
            from .text_translator import TextTranslator
            
            # 使用传入的配置，如果没有则使用默认配置
            translation_config = config if config is not None else self.config
            translator = TextTranslator(translation_config)
            
            # 准备翻译数据
            segments_for_translation = []
            for segment in optimized_segments:
                segments_for_translation.append({
                    "start": segment.get("start", 0.0),
                    "end": segment.get("end", 0.0),
                    "text": segment.get("text", "")
                })
            
            # 执行翻译
            translation_result = translator.translate_segments(segments_for_translation, output_dir)
            
            if translation_result["success"]:
                translated_segments = translation_result.get("translated_segments", [])
                translation_info = translation_result.get("translation_info", {})
                
                # 检查是否跳过了翻译
                if translation_info.get("method") == "skip_translation":
                    self.logger.info(f"🚀 翻译优化生效: {translation_info.get('reason', '')}")
                
                # 合并优化和翻译结果
                final_segments = []
                for i, (optimized, translated) in enumerate(zip(optimized_segments, translated_segments)):
                    final_segments.append({
                        **optimized,
                        "translated_text": translated.get("translated_text", ""),
                        "translation_info": translated.get("translation_info", {})
                    })
                optimized_segments = final_segments
                self.logger.info(f"✅ 独立翻译完成，处理了 {len(translated_segments)} 个分段")
            else:
                self.logger.warning("翻译失败，使用原始优化分段")
            
            # 保存所有处理结果
            transcription_result = self._save_processing_results(
                result, optimized_segments, audio_path, output_dir
            )
            
            self.logger.info("语音识别、分段优化和翻译完成")
            return transcription_result
            
        except Exception as e:
            self.logger.error(f"语音识别、分段优化和翻译失败: {e}")
            raise
    
    def detect_language(self, audio_path: str) -> Dict[str, Any]:
        """
        检测音频语言
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            语言检测结果
        """
        if not validate_file_path(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        self.logger.info(f"开始语言检测: {audio_path}")
        
        try:
            if self.backend == "faster-whisper":
                # 使用 Faster-Whisper 进行语言检测
                segments, info = self.model.transcribe(audio_path, language=None, task="transcribe", beam_size=1, best_of=1, temperature=0.0, patience=1.0, length_penalty=1.0, repetition_penalty=1.0, no_repeat_ngram_size=0, initial_prompt=None, prefix=None, suppress_blank=True, suppress_tokens=[-1], without_timestamps=True, max_initial_timestamp=0.0, word_timestamps=False, vad_filter=False)
                
                detected_language = info.language if hasattr(info, 'language') else "auto"
                confidence = getattr(info, 'language_probability', 1.0)
                all_probs = getattr(info, 'all_language_probs', {})
                
                result = {
                    "detected_language": detected_language,
                    "confidence": confidence,
                    "all_probabilities": all_probs,
                    "audio_path": audio_path
                }
            else:
                # 使用原生 Whisper 进行语言检测
                if not WHISPER_AVAILABLE:
                    raise ImportError("原生 Whisper 不可用")
                
                audio = whisper.load_audio(audio_path)
                audio = whisper.pad_or_trim(audio)
                
                # 检测语言
                mel = whisper.log_mel_spectrogram(audio).to(self.model.device)
                _, probs = self.model.detect_language(mel)
                
                # 获取最可能的语言
                detected_language = max(probs, key=probs.get)
                confidence = probs[detected_language]
                
                result = {
                    "detected_language": detected_language,
                    "confidence": confidence,
                    "all_probabilities": probs,
                    "audio_path": audio_path
                }
            
            self.logger.info(f"语言检测完成: {detected_language} (置信度: {confidence:.3f})")
            return result
            
        except Exception as e:
            self.logger.error(f"语言检测失败: {e}")
            raise
    
    def _process_transcription_result(self, result: Dict[str, Any], audio_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        处理转录结果
        
        Args:
            result: Whisper原始结果
            audio_path: 音频文件路径
            output_dir: 输出目录
            
        Returns:
            处理后的转录结果
        """
        # 提取基本信息
        text = result.get("text", "").strip()
        language = result.get("language", "unknown")
        
        # 创建输出目录
        if output_dir:
            create_output_dir(output_dir)
            
            # 保存转录文本
            input_name = Path(audio_path).stem
            safe_name = safe_filename(input_name)
            text_file = os.path.join(output_dir, f"{safe_name}_transcription.txt")
            
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(text)
        else:
            text_file = None
        
        return {
            "success": True,
            "text": text,
            "language": language,
            "audio_path": audio_path,
            "text_file": text_file,
            "processing_info": {
                "model_size": self.model_size,
                "task": self.task,
                "language_detected": language
            }
        }
    
    def _process_transcription_result_with_output_manager(self, result: Dict[str, Any], audio_path: str, output_manager: OutputManager, apply_optimization: bool = False) -> Dict[str, Any]:
        """
        使用OutputManager处理转录结果
        
        Args:
            result: Whisper原始结果
            audio_path: 音频文件路径
            output_manager: 输出管理器实例
            apply_optimization: 是否应用分段优化（已废弃，保留仅为兼容性）
            
        Returns:
            处理后的转录结果
        """
        # 提取基本信息
        text = result.get("text", "").strip()
        language = result.get("language", "unknown")
        segments = result.get("segments", [])
        
        # 处理时间段信息
        processed_segments = []
        for segment in segments:
            processed_segments.append({
                "start": segment.get("start", 0.0),
                "end": segment.get("end", 0.0),
                "text": segment.get("text", "").strip(),
                "words": segment.get("words", []),
                "speaker_id": segment.get("speaker_id")  # 保留speaker_id（如果存在）
            })
        
        # 不再使用内置的_optimize_segments，分段优化由外部方法（punctuation/semantic）处理
        self.logger.info(f"处理转录结果: {len(processed_segments)} 个分段")
        
        # 使用OutputManager生成文件路径
        transcription_file = output_manager.get_file_path(StepNumbers.STEP_4, "whisper_raw_transcription")
        word_timestamps_file = output_manager.get_file_path(StepNumbers.STEP_4, "whisper_raw_word_timestamps")
        segments_txt_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_txt")
        segments_json_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
        
        # 保存 Whisper 原始输出（用于调试）
        raw_result_file = output_manager.get_file_path(StepNumbers.STEP_4, "whisper_raw")
        with open(raw_result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 保存 Whisper 原始分段（可读格式）
        raw_segments_file = output_manager.get_file_path(StepNumbers.STEP_4, "whisper_raw_segments")
        with open(raw_segments_file, 'w', encoding='utf-8') as f:
            f.write("Whisper 原始分段:\n")
            f.write("=" * 60 + "\n\n")
            for i, seg in enumerate(result.get("segments", [])):
                f.write(f"分段 {i+1}:\n")
                f.write(f"  时间: {seg.get('start', 0):.3f}s - {seg.get('end', 0):.3f}s\n")
                f.write(f"  文本: {seg.get('text', '')}\n")
                f.write(f"  单词数: {len(seg.get('words', []))}\n\n")
        
        # 保存转录文本
        with open(transcription_file, 'w', encoding='utf-8') as f:
            f.write(text)
        
        # 保存单词级时间戳（从原始 result 提取，确保完整）
        word_timestamps = []
        for segment in result.get("segments", []):  # 改用 result 而不是 processed_segments
            for word in segment.get("words", []):
                word_timestamps.append({
                    "word": word.get("word", ""),
                    "start": word.get("start", 0.0),
                    "end": word.get("end", 0.0),
                    "probability": word.get("probability", 0.0)
                })
        
        with open(word_timestamps_file, 'w', encoding='utf-8') as f:
            f.write("Whisper 原始单词时间戳（完整数据）:\n")
            f.write("=" * 60 + "\n\n")
            for word_info in word_timestamps:
                f.write(f"{word_info['start']:.3f} - {word_info['end']:.3f}: {word_info['word']} (prob: {word_info['probability']:.3f})\n")
        
        # 保存分段文本
        with open(segments_txt_file, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(processed_segments):
                f.write(f"Segment {i+1} ({segment['start']:.3f}s - {segment['end']:.3f}s):\n")
                f.write(f"{segment['text']}\n\n")
        
        # 保存分段JSON数据
        with open(segments_json_file, 'w', encoding='utf-8') as f:
            json.dump(processed_segments, f, ensure_ascii=False, indent=2)
        
        # 记录日志
        self.logger.info(f"📊 单词时间戳统计: 总计 {len(word_timestamps)} 个单词")
        if word_timestamps:
            self.logger.info(f"  时间范围: {word_timestamps[0]['start']:.2f}s - {word_timestamps[-1]['end']:.2f}s")
        
        output_manager.log(f"转录文件已保存:")
        output_manager.log(f"  - 转录文本: {transcription_file}")
        output_manager.log(f"  - 单词时间戳: {word_timestamps_file}")
        output_manager.log(f"  - 分段文本: {segments_txt_file}")
        output_manager.log(f"  - 分段JSON: {segments_json_file}")
        output_manager.log(f"  - Whisper原始输出: {raw_result_file}")
        output_manager.log(f"  - Whisper原始分段: {raw_segments_file}")
        
        return {
            "success": True,
            "text": text,
            "language": language,
            "audio_path": audio_path,
            "transcription_file": transcription_file,
            "word_timestamps_file": word_timestamps_file,
            "segments_txt_file": segments_txt_file,
            "segments_json_file": segments_json_file,
            "segments": processed_segments,
            "processing_info": {
                "model_size": self.model_size,
                "task": self.task,
                "language_detected": language,
                "segments_count": len(processed_segments)
            }
        }
    
    def _process_detailed_transcription_result(self, result: Dict[str, Any], audio_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        处理详细转录结果
        
        Args:
            result: Whisper原始结果
            audio_path: 音频文件路径
            output_dir: 输出目录
            
        Returns:
            处理后的详细转录结果
        """
        # 提取基本信息
        text = result.get("text", "").strip()
        language = result.get("language", "unknown")
        segments = result.get("segments", [])
        
        # 处理时间段信息，并进行后处理优化
        processed_segments = []
        for segment in segments:
            processed_segments.append({
                "start": segment.get("start", 0.0),
                "end": segment.get("end", 0.0),
                "text": segment.get("text", "").strip(),
                "words": segment.get("words", [])
            })
        
        # 不再使用内置的_optimize_segments，分段优化由外部方法（punctuation/semantic）处理
        
        # 创建输出目录
        if output_dir:
            create_output_dir(output_dir)
            
            # 保存详细转录结果
            input_name = Path(audio_path).stem
            safe_name = safe_filename(input_name)
            
            # 保存文本文件
            text_file = os.path.join(output_dir, f"{safe_name}_transcription.txt")
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(text)
            
        else:
            text_file = None
        
        return {
            "success": True,
            "text": text,
            "language": language,
            "segments": processed_segments,
            "audio_path": audio_path,
            "text_file": text_file,
            "processing_info": {
                "model_size": self.model_size,
                "task": self.task,
                "language_detected": language,
                "segment_count": len(processed_segments)
            }
        }
    
    def _save_processing_results(self, whisper_result: Dict[str, Any], 
                               optimized_segments: List[Dict[str, Any]], 
                               audio_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        保存所有处理结果到文件并返回汇总信息
        
        Args:
            whisper_result: Whisper原始结果
            optimized_segments: 优化后的分段（可能包含翻译结果）
            audio_path: 音频文件路径
            output_dir: 输出目录
            
        Returns:
            包含所有文件路径和处理信息的字典
        """
        # 提取基本信息
        text = whisper_result.get("text", "").strip()
        language = whisper_result.get("language", "unknown")
        whisper_segments = whisper_result.get("segments", [])
        
        # 创建输出目录
        if output_dir:
            create_output_dir(output_dir)
            
            # 保存转录文本
            input_name = Path(audio_path).stem
            safe_name = safe_filename(input_name)
            
            # 保存完整文本
            text_file = os.path.join(output_dir, f"{safe_name}_transcription.txt")
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(text)
            
        # 验证分段数据
        self._validate_segment_data(optimized_segments)
        
        # 保存优化后的分段（优先显示翻译后的中文）
        # 根据分段方法选择文件名
        segmentation_config = self.whisper_config.get("segmentation", {})
        segmentation_method = segmentation_config.get("method", "rule_based")
        
        if segmentation_method == "punctuation":
            segments_file = os.path.join(output_dir, f"{safe_name}_punctuation_segments.txt")
        else:
            segments_file = os.path.join(output_dir, f"{safe_name}_optimized_segments.txt")
        
        # 确保输出目录存在
        if output_dir:
            create_output_dir(output_dir)
        
        with open(segments_file, 'w', encoding='utf-8') as f:
            for segment in optimized_segments:
                # 保存原始分段文本（不包含翻译结果）
                text_to_save = segment.get('text', '')
                f.write(f"[{segment['start']:.2f}s - {segment['end']:.2f}s] {text_to_save}\n")
        
        # 保存翻译结果到单独的文件
        translation_file = os.path.join(output_dir, f"{safe_name}_translation_result.txt")
        with open(translation_file, 'w', encoding='utf-8') as f:
            for segment in optimized_segments:
                if 'translated_text' in segment:
                    f.write(f"[{segment['start']:.2f}s - {segment['end']:.2f}s] {segment['translated_text']}\n")
        
        return {
            "success": True,
            "text": text,
            "language": language,
            "segments": optimized_segments,
            "audio_path": audio_path,
            "text_file": text_file,
            "segments_file": segments_file,
            "translation_file": translation_file,
            "processing_info": {
                "model_size": self.model_size,
                "task": self.task,
                "language_detected": language,
                "segment_count": len(optimized_segments),
                "segment_optimized": self.segment_optimizer is not None
            }
        }
    
    def _validate_segment_data(self, segments: List[Dict[str, Any]]) -> None:
        """验证分段数据的完整性和一致性"""
        self.logger.info("🔍 验证分段数据...")
        
        for i, segment in enumerate(segments):
            start = segment.get("start", 0.0)
            end = segment.get("end", 0.0)
            text = segment.get("text", "")
            audio_path = segment.get("audio_path", "")
            
            duration = end - start
            
            self.logger.info(f"分段 {i}: {start:.2f}s - {end:.2f}s ({duration:.2f}s)")
            self.logger.info(f"  文本长度: {len(text)} 字符")
            self.logger.info(f"  音频文件: {audio_path}")
            
            # 检查时间戳合理性
            if end <= start:
                self.logger.error(f"  ❌ 时间戳错误: end({end}) <= start({start})")
            
            # 检查音频文件是否存在
            if audio_path and not os.path.exists(audio_path):
                self.logger.error(f"  ❌ 音频文件不存在: {audio_path}")
            
            # 检查文本是否为空
            if not text.strip():
                self.logger.warning(f"  ⚠️ 文本为空")
    
    def get_available_models(self) -> List[str]:
        """
        获取可用的模型列表
        
        Returns:
            可用模型列表
        """
        return ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
    
    def get_supported_languages(self) -> List[str]:
        """
        获取支持的语言列表
        
        Returns:
            支持的语言列表
        """
        if not WHISPER_AVAILABLE:
            return []
        return list(whisper.tokenizer.LANGUAGES.keys())
    
    def transcribe_with_progress(self, audio_path: str, output_dir: Optional[str] = None,
                                progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        带进度回调的转录
        
        Args:
            audio_path: 音频文件路径
            output_dir: 输出目录（可选）
            progress_callback: 进度回调函数
            
        Returns:
            转录结果字典
        """
        if progress_callback:
            progress_callback(0.0, "开始语音识别...")
        
        # 执行转录
        result = self.transcribe_audio(audio_path, output_dir)
        
        if progress_callback:
            progress_callback(100.0, "语音识别完成")
        
        return result
    
    def _save_whisper_word_timestamps(self, whisper_result: Dict[str, Any], audio_path: str, output_dir: str):
        """保存Whisper原始单词时间戳到文件"""
        try:
            self.logger.info("🚀 开始保存Whisper原始单词时间戳...")
            
            input_name = Path(audio_path).stem
            safe_name = safe_filename(input_name)
            
            self.logger.info(f"输入文件名: {input_name}, 安全文件名: {safe_name}")
            
            # 保存原始Whisper结果
            whisper_file = os.path.join(output_dir, f"{safe_name}_whisper_raw.json")
            self.logger.info(f"保存原始Whisper结果到: {whisper_file}")
            
            with open(whisper_file, 'w', encoding='utf-8') as f:
                json.dump(whisper_result, f, ensure_ascii=False, indent=2)
            
            # 保存单词时间戳到单独文件
            word_timestamps_file = os.path.join(output_dir, f"{safe_name}_word_timestamps.txt")
            self.logger.info(f"保存单词时间戳到: {word_timestamps_file}")
            
            with open(word_timestamps_file, 'w', encoding='utf-8') as f:
                f.write("Whisper原始单词时间戳:\n")
                f.write("=" * 50 + "\n\n")
                
                segments = whisper_result.get("segments", [])
                self.logger.info(f"找到 {len(segments)} 个分段")
                
                for i, segment in enumerate(segments):
                    f.write(f"分段 {i+1}: {segment.get('start', 0):.2f}s - {segment.get('end', 0):.2f}s\n")
                    f.write(f"文本: {segment.get('text', '')}\n")
                    f.write("单词时间戳:\n")
                    
                    words = segment.get('words', [])
                    self.logger.info(f"分段 {i+1} 包含 {len(words)} 个单词")
                    
                    for j, word in enumerate(words):
                        f.write(f"  {j+1:2d}. {word.get('word', ''):<15} {word.get('start', 0):6.2f}s - {word.get('end', 0):6.2f}s (概率: {word.get('probability', 0):.3f})\n")
                    f.write("\n")
                
                # 统计信息
                total_words = sum(len(segment.get('words', [])) for segment in segments)
                max_time = max(segment.get('end', 0) for segment in segments) if segments else 0
                f.write(f"\n统计信息:\n")
                f.write(f"总分段数: {len(segments)}\n")
                f.write(f"总单词数: {total_words}\n")
                f.write(f"最大时间戳: {max_time:.2f}秒\n")
                
                self.logger.info(f"统计信息: 总分段数={len(segments)}, 总单词数={total_words}, 最大时间戳={max_time:.2f}秒")
            
            self.logger.info(f"✅ Whisper原始结果已保存: {whisper_file}")
            self.logger.info(f"✅ 单词时间戳已保存: {word_timestamps_file}")
            
        except Exception as e:
            self.logger.error(f"❌ 保存Whisper原始结果失败: {e}")
            import traceback
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
    
    def _save_optimized_segments(self, segments: List[Dict], segments_txt_file: str, segments_json_file: str):
        """
        保存优化后的分段文件
        
        Args:
            segments: 优化后的分段列表
            segments_txt_file: 文本格式分段文件路径
            segments_json_file: JSON格式分段文件路径
        """
        # 保存为文本格式
        with open(segments_txt_file, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments):
                start = segment.get('start', 0)
                end = segment.get('end', 0)
                text = segment.get('text', '').strip()
                f.write(f"[{i+1}] {start:.2f}s - {end:.2f}s: {text}\n")
        
        # 保存为JSON格式
        with open(segments_json_file, 'w', encoding='utf-8') as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)

