"""
音色克隆模块
使用IndexTTS2为每个段落生成中文语音，保持原始说话者的音色特征
"""

import os
# 修复protobuf兼容性问题：必须在导入任何模块之前设置环境变量
# 这可以解决protobuf版本过新（>3.20.x）导致的兼容性问题
if "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION" not in os.environ:
    os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import logging
import json
import subprocess
import tempfile
import time
import gc
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils import validate_file_path, create_output_dir, safe_filename
from .output_manager import OutputManager
from .gpu_monitor import GPUMonitor


class VoiceCloner:
    """音色克隆器类"""
    
    # 类级单例变量
    _instance = None
    _model = None
    _initialized = False
    
    def __new__(cls, config: Dict[str, Any]):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super(VoiceCloner, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化音色克隆器
        
        Args:
            config: 配置字典
        """
        # 避免重复初始化
        if self._initialized:
            return
            
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 音色克隆配置
        self.cloning_config = config.get("voice_cloning", {})
        self.model_path = self.cloning_config.get("model_path", "./models/indexTTS2")
        self.device = self.cloning_config.get("device", "cpu")
        self.sample_rate = self.cloning_config.get("sample_rate", 16000)
        self.max_text_tokens = self.cloning_config.get("max_text_tokens", 600)
        self.max_mel_tokens = self.cloning_config.get("max_mel_tokens", 1815)
        
        # 并行克隆配置
        self.enable_parallel = self.cloning_config.get("enable_parallel", True)
        self.max_parallel_workers = self.cloning_config.get("max_parallel_workers", 2)
        
        # 添加锁来保护GPU访问，避免CUDA错误污染GPU状态
        # 虽然IndexTTS2的infer方法本身是线程安全的，但CUDA错误会污染GPU状态
        # 使用锁可以确保同一时间只有一个线程访问GPU，避免并发CUDA错误
        self._gpu_lock = threading.RLock()
        
        # GPU监控器
        self.gpu_monitor = GPUMonitor(config)
        
        # 初始化IndexTTS2（只初始化一次）
        self._init_indexTTS2()
        self._initialized = True
    
    def _init_indexTTS2(self):
        """初始化IndexTTS2"""
        try:
            self.logger.info("初始化IndexTTS2...")
            
            # 检查依赖
            self._check_dependencies()
            
            # 直接导入IndexTTS2（避免重复初始化）
            if self._model is None:
                self.logger.info("首次加载IndexTTS2模型...")
                from indextts.infer_v2 import IndexTTS2
                
                # 初始化IndexTTS2模型（启用FP16 + CUDA Kernel优化）
                self._model = IndexTTS2(
                    cfg_path=os.path.join(self.model_path, "checkpoints/config.yaml"),
                    model_dir=os.path.join(self.model_path, "checkpoints"),
                    use_fp16=True,        # 启用FP16精度，提升速度并减少显存占用
                    use_cuda_kernel=True, # 启用CUDA kernel加速
                    use_deepspeed=False
                )
                self.logger.info("✅ IndexTTS2模型加载完成")
            else:
                self.logger.info("✅ IndexTTS2模型已存在，复用现有实例")
            
            self.logger.info("IndexTTS2初始化完成")
            
        except Exception as e:
            self.logger.error(f"IndexTTS2初始化失败: {e}")
            raise
    
    def _check_dependencies(self):
        """检查依赖项"""
        required_packages = ["torch", "torchaudio", "transformers", "numpy"]
        
        for package in required_packages:
            try:
                __import__(package)
                self.logger.info(f"✓ {package} 已安装")
            except ImportError:
                self.logger.warning(f"✗ {package} 未安装")
    
    def clone_voice(self, reference_audio: str, text: str, output_path: str, 
                   speaker_id: Optional[str] = None) -> Dict[str, Any]:
        """
        克隆单个语音
        
        Args:
            reference_audio: 参考音频文件路径
            text: 要合成的文本
            output_path: 输出音频文件路径
            speaker_id: 说话者ID（可选）
            
        Returns:
            克隆结果字典
        """
        try:
            self.logger.info(f"开始音色克隆: {text[:50]}...")
            
            # 验证输入文件
            if not validate_file_path(reference_audio):
                raise FileNotFoundError(f"参考音频文件不存在: {reference_audio}")
            
            # 检查文本长度
            if len(text) > self.max_text_tokens:
                self.logger.warning(f"文本长度超过限制: {len(text)} > {self.max_text_tokens}")
                text = text[:self.max_text_tokens]
            
            # 转义文本中的特殊字符，避免语法错误
            text = text.replace("'", "\\'")  # 转义单引号
            text = text.replace('"', '\\"')  # 转义双引号
            text = text.replace('\n', '\\n')  # 转义换行符
            text = text.replace('\r', '\\r')  # 转义回车符
            text = text.replace('\t', '\\t')  # 转义制表符
            
            # 创建输出目录
            output_dir = os.path.dirname(output_path)
            create_output_dir(output_dir)
            
            # 执行音色克隆
            success = self._run_indexTTS2(reference_audio, text, output_path, speaker_id)
            
            if success:
                result = {
                    "success": True,
                    "reference_audio": reference_audio,
                    "text": text,
                    "output_path": output_path,
                    "speaker_id": speaker_id,
                    "processing_info": {
                        "text_length": len(text),
                        "model_path": self.model_path,
                        "device": self.device
                    }
                }
                self.logger.info(f"音色克隆完成: {output_path}")
            else:
                result = {
                    "success": False,
                    "error": "IndexTTS2执行失败",
                    "reference_audio": reference_audio,
                    "text": text,
                    "output_path": output_path
                }
                self.logger.error("音色克隆失败")
            
            return result
            
        except Exception as e:
            self.logger.error(f"音色克隆失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "reference_audio": reference_audio,
                "text": text,
                "output_path": output_path
            }
    
    def clone_segments(self, segments: List[Dict[str, Any]], 
                      output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        克隆多个音频段落
        
        Args:
            segments: 音频段落列表
            output_dir: 输出目录
            
        Returns:
            克隆结果字典
        """
        if not segments:
            return {
                "success": False,
                "error": "没有提供音频段落"
            }
        
        self.logger.info(f"开始克隆 {len(segments)} 个音频段落")
        
        # 创建输出目录
        if output_dir:
            create_output_dir(output_dir)
        
        cloned_segments = []
        cloning_results = []
        
        try:
            for i, segment in enumerate(segments):
                self.logger.info(f"克隆段落 {i+1}/{len(segments)}")
                
                # 获取段落信息
                # 优先使用绑定阶段提供的稳定参考音频
                audio_path = segment.get("reference_audio_path", segment.get("audio_path", ""))
                text = segment.get("translated_text", "")
                original_text = segment.get("original_text", "")
                
                if not audio_path or not text:
                    self.logger.warning(f"段落 {i+1} 缺少必要信息")
                    continue
                
                # 生成输出文件名
                output_filename = f"cloned_{i:02d}.wav"
                output_path = os.path.join(output_dir, output_filename) if output_dir else f"output/cloned_{i:02d}.wav"
                
                # 执行音色克隆
                cloning_result = self.clone_voice(audio_path, text, output_path, f"speaker_{i}")
                cloning_results.append(cloning_result)
                
                if cloning_result["success"]:
                    # 创建克隆后的段落
                    cloned_segment = {
                        **segment,
                        "cloned_audio_path": output_path,
                        "cloning_info": cloning_result["processing_info"]
                    }
                    cloned_segments.append(cloned_segment)
                    
                    # 保存克隆结果到文件
                    if output_dir:
                        self._save_cloning_result(cloned_segment, output_dir, i)
                
                self.logger.info(f"段落 {i+1} 克隆完成")
            
            # 生成克隆报告
            cloning_report = self._generate_cloning_report(cloning_results)
            
            result = {
                "success": True,
                "total_segments": len(segments),
                "cloned_segments": len(cloned_segments),
                "cloned_segments": cloned_segments,
                "cloning_results": cloning_results,
                "cloning_report": cloning_report,
                "output_dir": output_dir
            }
            
            self.logger.info(f"所有段落克隆完成: {len(cloned_segments)}/{len(segments)}")
            return result
            
        except Exception as e:
            self.logger.error(f"批量克隆失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "cloned_segments": cloned_segments,
                "cloning_results": cloning_results
            }
    
    def clone_segments_with_output_manager(self, segments: List[Dict[str, Any]], 
                                          output_manager: OutputManager) -> Dict[str, Any]:
        """
        使用OutputManager克隆多个音频段落
        
        Args:
            segments: 音频段落列表
            output_manager: 输出管理器实例
            
        Returns:
            克隆结果字典
        """
        if not segments:
            return {
                "success": False,
                "error": "没有提供音频段落"
            }
        
        self.logger.info(f"开始克隆 {len(segments)} 个音频段落")
        output_manager.log(f"步骤7开始: 音色克隆 {len(segments)} 个段落")
        
        cloned_segments = []
        cloning_results = []
        
        try:
            for i, segment in enumerate(segments):
                self.logger.info(f"克隆段落 {i+1}/{len(segments)}")
                output_manager.log(f"克隆段落 {i+1}/{len(segments)}")
                
                # 获取段落信息
                audio_path = segment.get("audio_path", "")
                text = segment.get("translated_text", "")
                original_text = segment.get("original_text", "")
                
                if not audio_path or not text:
                    self.logger.warning(f"段落 {i+1} 缺少必要信息")
                    output_manager.log(f"段落 {i+1} 缺少必要信息，跳过")
                    continue
                
                # 使用OutputManager生成输出文件路径
                output_path = output_manager.get_segment_path(i)
                
                # 执行音色克隆
                clone_result = self.clone_voice(audio_path, text, output_path)
                cloning_results.append(clone_result)
                
                if clone_result["success"]:
                    cloned_segment = {
                        **segment,
                        "cloned_audio_path": output_path,
                        "cloning_result": clone_result
                    }
                    cloned_segments.append(cloned_segment)
                    output_manager.log(f"段落 {i+1} 克隆成功: {output_path}")
                else:
                    self.logger.error(f"段落 {i+1} 克隆失败: {clone_result.get('error', '未知错误')}")
                    output_manager.log(f"段落 {i+1} 克隆失败: {clone_result.get('error', '未知错误')}")
            
            # 构建结果
            result = {
                "success": len(cloned_segments) > 0,
                "total_segments": len(segments),
                "cloned_segments": len(cloned_segments),
                "failed_segments": len(segments) - len(cloned_segments),
                "cloned_segments": cloned_segments,
                "cloning_results": cloning_results,
                "processing_info": {
                    "model_path": self.model_path,
                    "device": self.device,
                    "sample_rate": self.sample_rate
                }
            }
            
            self.logger.info(f"所有段落克隆完成: {len(cloned_segments)}/{len(segments)}")
            output_manager.log(f"步骤7完成: 音色克隆完成，{len(cloned_segments)}/{len(segments)} 个段落成功")
            return result
            
        except Exception as e:
            self.logger.error(f"批量克隆失败: {e}")
            output_manager.log(f"步骤7失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "cloned_segments": cloned_segments,
                "cloning_results": cloning_results
            }
    
    def clone_segments_parallel(self, segments: List[Dict[str, Any]], 
                               output_manager: OutputManager) -> Dict[str, Any]:
        """
        并行克隆多个音频段落
        
        Args:
            segments: 音频段落列表
            output_manager: 输出管理器实例
            
        Returns:
            克隆结果字典
        """
        if not segments:
            return {
                "success": False,
                "error": "没有提供音频段落"
            }
        
        self.logger.info(f"开始并行克隆 {len(segments)} 个音频段落")
        output_manager.log(f"步骤7开始: 并行音色克隆 {len(segments)} 个段落")
        
        # 记录开始时间
        start_time = time.time()
        
        # 记录GPU状态
        self.gpu_monitor.log_memory_status("并行克隆开始前")
        
        # 动态确定并行worker数量
        if self.enable_parallel:
            suggested_workers = self.gpu_monitor.suggest_parallel_workers(self.max_parallel_workers)
            actual_workers = min(suggested_workers, len(segments))
            self.logger.info(f"使用 {actual_workers} 个并行worker进行克隆")
            output_manager.log(f"使用 {actual_workers} 个并行worker进行克隆")
        else:
            actual_workers = 1
            self.logger.info("并行克隆已禁用，使用单线程模式")
            output_manager.log("并行克隆已禁用，使用单线程模式")
        
        cloned_segments = []
        cloning_results = []
        
        try:
            if actual_workers > 1:
                # 并行处理
                with ThreadPoolExecutor(max_workers=actual_workers) as executor:
                    # 提交所有任务
                    future_to_segment = {}
                    for i, segment in enumerate(segments):
                        future = executor.submit(
                            self._clone_single_segment_safe, 
                            segment, i, output_manager
                        )
                        future_to_segment[future] = (i, segment)
                    
                    # 收集结果
                    for future in as_completed(future_to_segment):
                        i, segment = future_to_segment[future]
                        try:
                            result = future.result()
                            cloning_results.append(result)
                            
                            if result["success"]:
                                cloned_segments.append(result["cloned_segment"])
                                output_manager.log(f"段落 {i+1} 并行克隆成功")
                            else:
                                self.logger.error(f"段落 {i+1} 并行克隆失败: {result.get('error', '未知错误')}")
                                output_manager.log(f"段落 {i+1} 并行克隆失败: {result.get('error', '未知错误')}")
                                
                        except Exception as e:
                            error_msg = str(e)
                            self.logger.error(f"段落 {i+1} 并行克隆异常: {error_msg}")
                            output_manager.log(f"段落 {i+1} 并行克隆异常: {error_msg}")
                            
                            # 如果是CUDA错误，等待并尝试清理GPU状态
                            if "CUDA error" in error_msg or "device-side assert" in error_msg:
                                try:
                                    import torch
                                    if torch.cuda.is_available():
                                        # 等待GPU恢复
                                        time.sleep(1.0)
                                        # 尝试重置CUDA错误状态
                                        try:
                                            torch.cuda.synchronize()
                                        except:
                                            pass
                                        # 清理GPU缓存
                                        try:
                                            torch.cuda.empty_cache()
                                            self.logger.info(f"段落 {i+1} CUDA错误后已清理GPU状态")
                                        except Exception as cleanup_error:
                                            self.logger.warning(f"清理GPU状态时出错（可能GPU状态已损坏）: {cleanup_error}")
                                except Exception as cleanup_error:
                                    self.logger.warning(f"处理CUDA错误时出错: {cleanup_error}")
                            
                            cloning_results.append({
                                "success": False,
                                "error": error_msg,
                                "segment_index": i
                            })
            else:
                # 单线程处理
                for i, segment in enumerate(segments):
                    result = self._clone_single_segment_safe(segment, i, output_manager)
                    cloning_results.append(result)
                    
                    if result["success"]:
                        cloned_segments.append(result["cloned_segment"])
                        output_manager.log(f"段落 {i+1} 克隆成功")
                    else:
                        self.logger.error(f"段落 {i+1} 克隆失败: {result.get('error', '未知错误')}")
                        output_manager.log(f"段落 {i+1} 克隆失败: {result.get('error', '未知错误')}")
            
            # 清理GPU缓存
            self.gpu_monitor.clear_cache()
            
            # 记录结束时间和GPU状态
            end_time = time.time()
            processing_time = end_time - start_time
            self.gpu_monitor.log_memory_status("并行克隆完成后")
            
            # 构建结果
            result = {
                "success": len(cloned_segments) > 0,
                "total_segments": len(segments),
                "cloned_segments": len(cloned_segments),
                "failed_segments": len(segments) - len(cloned_segments),
                "cloned_segments": cloned_segments,
                "cloning_results": cloning_results,
                "processing_info": {
                    "model_path": self.model_path,
                    "device": self.device,
                    "sample_rate": self.sample_rate,
                    "parallel_workers": actual_workers,
                    "processing_time": processing_time,
                    "enable_parallel": self.enable_parallel
                }
            }
            
            self.logger.info(f"并行克隆完成: {len(cloned_segments)}/{len(segments)} 个段落成功，耗时 {processing_time:.1f}秒")
            output_manager.log(f"步骤7完成: 并行音色克隆完成，{len(cloned_segments)}/{len(segments)} 个段落成功，耗时 {processing_time:.1f}秒")
            return result
            
        except Exception as e:
            self.logger.error(f"并行克隆失败: {e}")
            output_manager.log(f"步骤7失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "cloned_segments": cloned_segments,
                "cloning_results": cloning_results
            }
    
    def _clone_single_segment_safe(self, segment: Dict[str, Any], 
                                  segment_index: int, 
                                  output_manager: OutputManager) -> Dict[str, Any]:
        """
        线程安全的单个段落克隆方法
        
        使用锁来保护GPU访问，避免CUDA错误污染GPU状态。
        虽然IndexTTS2的infer方法本身是线程安全的，但CUDA错误会污染GPU状态，
        导致其他并行任务也失败。使用锁可以确保同一时间只有一个线程访问GPU。
        
        Args:
            segment: 段落信息
            segment_index: 段落索引
            output_manager: 输出管理器实例
        
        Returns:
            克隆结果字典
        """
        try:
            # 获取段落信息（不需要锁，只是读取数据）
            audio_path = segment.get("reference_audio_path", segment.get("audio_path", ""))
            text = segment.get("translated_text", "")
            original_text = segment.get("original_text", "")
            
            if not audio_path or not text:
                return {
                    "success": False,
                    "error": "段落缺少必要信息",
                    "segment_index": segment_index
                }
            
            # 使用OutputManager生成输出文件路径（不需要锁）
            output_path = output_manager.get_cloned_segment_path(segment_index)
            
            # 检查输出文件是否已存在，如果存在则跳过
            if os.path.exists(output_path):
                self.logger.info(f"⏭️  跳过已存在的segment {segment_index}: {output_path}")
                cloned_segment = {
                    **segment,
                    "cloned_audio_path": output_path,
                    "cloning_result": {"success": True, "skipped": True}
                }
                return {
                    "success": True,
                    "cloned_segment": cloned_segment,
                    "segment_index": segment_index,
                    "skipped": True
                }
            
            # 使用锁保护GPU访问，避免CUDA错误污染GPU状态
            with self._gpu_lock:
                clone_result = self.clone_voice(audio_path, text, output_path)
            
            if clone_result["success"]:
                cloned_segment = {
                    **segment,
                    "cloned_audio_path": output_path,
                    "cloning_result": clone_result
                }
                return {
                    "success": True,
                    "cloned_segment": cloned_segment,
                    "segment_index": segment_index
                }
            else:
                return {
                    "success": False,
                    "error": clone_result.get("error", "克隆失败"),
                    "segment_index": segment_index
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "segment_index": segment_index
            }
    
    def _run_indexTTS2(self, reference_audio: str, text: str, output_path: str, 
                     speaker_id: Optional[str] = None) -> bool:
        """运行IndexTTS2进行音色克隆"""
        try:
            # 使用直接调用IndexTTS2模型
            if self._model is None:
                self.logger.error("IndexTTS2模型未初始化")
                return False
            
            # 直接调用IndexTTS2进行推理
            self.logger.info(f"开始音色克隆: {text[:50]}...")
            
            # 调用IndexTTS2的infer方法
            self._model.infer(
                spk_audio_prompt=reference_audio,
                text=text,
                output_path=output_path,
                use_emo_text=False,  # 使用参考音频的情绪
                emo_alpha=0.65,  # 与Web UI保持一致
                use_random=False,
                verbose=True
            )
            
            # 检查输出文件是否生成
            if os.path.exists(output_path):
                self.logger.info(f"✅ 音色克隆成功: {output_path}")
                return True
            else:
                self.logger.error(f"❌ 音色克隆失败: 输出文件不存在 {output_path}")
                return False
            
        except RuntimeError as e:
            error_msg = str(e)
            # 检查是否是CUDA错误
            if "CUDA error" in error_msg or "device-side assert" in error_msg:
                self.logger.error(f"IndexTTS2执行失败: CUDA错误 - {error_msg}")
                # CUDA错误后，等待一段时间让GPU恢复，然后尝试清理
                try:
                    import torch
                    if torch.cuda.is_available():
                        # 等待GPU恢复（不立即清理，因为清理可能也会失败）
                        time.sleep(1.0)
                        # 尝试重置CUDA错误状态
                        try:
                            torch.cuda.synchronize()
                        except:
                            pass
                        # 清理GPU缓存
                        try:
                            torch.cuda.empty_cache()
                            self.logger.info("已清理GPU缓存和同步CUDA状态")
                        except Exception as cleanup_error:
                            self.logger.warning(f"清理GPU缓存时出错（可能GPU状态已损坏）: {cleanup_error}")
                except Exception as cleanup_error:
                    self.logger.warning(f"处理CUDA错误时出错: {cleanup_error}")
            else:
                self.logger.error(f"IndexTTS2执行失败: {error_msg}")
            return False
        except Exception as e:
            self.logger.error(f"IndexTTS2执行失败: {e}")
            return False
    
    def _use_python_api(self, reference_audio: str, text: str, output_path: str, 
                       config_data: Dict[str, Any]) -> bool:
        """使用IndexTTS2虚拟环境中的Python API"""
        try:
            self.logger.info("使用IndexTTS2虚拟环境中的Python API...")
            
            # 使用配置中的model_path（转换为绝对路径）
            index_tts_dir = os.path.abspath(self.model_path)
            venv_python = os.path.join(index_tts_dir, ".venv", "bin", "python")
            
            # 构建Python代码
            python_code = f"""
import os
import sys
os.chdir('{index_tts_dir}')

# 设置环境变量
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
os.environ['HF_HOME'] = '{index_tts_dir}/.cache/hf'
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'  # 修复protobuf兼容性问题

# 导入IndexTTS2
from indextts.infer_v2 import IndexTTS2

# 初始化IndexTTS2
tts = IndexTTS2(
    cfg_path="checkpoints/config.yaml", 
    model_dir="checkpoints", 
    use_fp16=True, 
    use_cuda_kernel=True, 
    use_deepspeed=False
)

# 执行音色克隆
tts.infer(
    spk_audio_prompt='{os.path.abspath(reference_audio)}',
    text='{text}',
    output_path='{os.path.abspath(output_path)}',
    verbose=True,
    use_emo_text=False,
    emo_alpha=0.65,  # 与Web UI保持一致
    use_random=False
)
"""
            
            # 执行命令
            result = subprocess.run(
                [venv_python, "-c", python_code],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=index_tts_dir,
                env={
                    **os.environ,
                    'HF_ENDPOINT': 'https://hf-mirror.com',
                    'HF_HOME': f'{index_tts_dir}/.cache/hf',
                    'PYTHONUNBUFFERED': '1',
                    'PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION': 'python'  # 修复protobuf兼容性问题
                }
            )
            
            if result.returncode == 0:
                self.logger.info("IndexTTS2虚拟环境Python API调用成功")
                return True
            else:
                self.logger.error(f"IndexTTS2虚拟环境调用失败: {result.stderr}")
                return False
            
        except Exception as e:
            self.logger.error(f"IndexTTS2虚拟环境调用失败: {e}")
            return False
    
    def _use_command_line(self, reference_audio: str, text: str, output_path: str, 
                         config_data: Dict[str, Any]) -> bool:
        """使用命令行工具调用IndexTTS2"""
        try:
            self.logger.info("使用命令行工具调用IndexTTS2...")
            
            # 使用配置中的model_path（转换为绝对路径）
            index_tts_dir = os.path.abspath(self.model_path)
            venv_python = os.path.join(index_tts_dir, ".venv", "bin", "python")
            
            # 构建命令行参数
            cmd = [
                venv_python, "-c",
                f"""
import os
# 修复protobuf兼容性问题
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
os.chdir('{index_tts_dir}')
from indextts.infer_v2 import IndexTTS2
tts = IndexTTS2(cfg_path="checkpoints/config.yaml", model_dir="checkpoints", use_fp16=True, use_cuda_kernel=True, use_deepspeed=False)
tts.infer(spk_audio_prompt='{reference_audio}', text='{text}', output_path='{output_path}', verbose=True)
"""
            ]
            
            # 设置环境变量
            env = os.environ.copy()
            env['HF_ENDPOINT'] = "https://hf-mirror.com"
            env['HF_HOME'] = os.path.join(index_tts_dir, ".cache", "hf")
            env['PYTHONUNBUFFERED'] = "1"
            env['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = "python"  # 修复protobuf兼容性问题
            
            # 执行命令
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env, cwd=index_tts_dir)
            
            if result.returncode == 0:
                self.logger.info("命令行工具执行成功")
                return True
            else:
                self.logger.error(f"命令行工具执行失败: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"命令行工具调用失败: {e}")
            return False
    
    def _use_simulation(self, reference_audio: str, text: str, output_path: str, 
                       config_data: Dict[str, Any]) -> bool:
        """使用模拟实现（用于测试）"""
        try:
            self.logger.info("使用模拟实现进行音色克隆...")
            
            # 这里实现一个简单的模拟，实际项目中应该使用真实的IndexTTS2
            # 模拟过程：
            # 1. 加载参考音频
            # 2. 提取音色特征
            # 3. 生成目标文本的语音
            # 4. 保存输出音频
            
            # 由于这是模拟实现，我们简单地复制参考音频作为输出
            # 实际项目中应该使用真实的IndexTTS2模型
            
            import shutil
            shutil.copy2(reference_audio, output_path)
            
            self.logger.info("模拟实现完成")
            return True
            
        except Exception as e:
            self.logger.error(f"模拟实现失败: {e}")
            return False
    
    def _save_cloning_result(self, segment: Dict[str, Any], output_dir: str, index: int):
        """保存克隆结果到文件"""
        try:
            # 创建克隆结果文件
            result_file = os.path.join(output_dir, f"cloning_{index:02d}.json")
            
            result_data = {
                "segment_id": index,
                "original_text": segment.get("original_text", ""),
                "translated_text": segment.get("translated_text", ""),
                "cloned_audio_path": segment.get("cloned_audio_path", ""),
                "start_time": segment.get("start_time", 0),
                "end_time": segment.get("end_time", 0),
                "duration": segment.get("duration", 0),
                "cloning_info": segment.get("cloning_info", {})
            }
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"克隆结果已保存: {result_file}")
            
        except Exception as e:
            self.logger.error(f"保存克隆结果失败: {e}")
    
    def _generate_cloning_report(self, cloning_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成克隆报告"""
        total_segments = len(cloning_results)
        successful_clonings = sum(1 for result in cloning_results if result.get("success", False))
        
        # 计算克隆质量指标
        text_lengths = [len(result.get("text", "")) for result in cloning_results]
        
        report = {
            "total_segments": total_segments,
            "successful_clonings": successful_clonings,
            "success_rate": successful_clonings / total_segments if total_segments > 0 else 0,
            "average_text_length": sum(text_lengths) / len(text_lengths) if text_lengths else 0,
            "model_path": self.model_path,
            "device": self.device,
            "sample_rate": self.sample_rate
        }
        
        return report
