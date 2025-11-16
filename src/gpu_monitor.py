"""
GPU监控模块
用于监控GPU显存使用情况，动态建议并行worker数量
"""

import logging
import gc
import torch
from typing import Dict, Any, Optional


class GPUMonitor:
    """GPU监控器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化GPU监控器
        
        Args:
            config: 配置字典，包含gpu_monitor相关配置
        """
        self.logger = logging.getLogger(__name__)
        
        # 从配置中读取参数
        gpu_config = config.get('gpu_monitor', {}) if config else {}
        self.enabled = gpu_config.get('enable', True)
        self.log_interval = gpu_config.get('log_interval', 10)
        self.safety_margin_gb = gpu_config.get('safety_margin_gb', 5.0)
        
        # 检查CUDA是否可用
        self.cuda_available = torch.cuda.is_available()
        if not self.cuda_available:
            self.logger.warning("CUDA不可用，GPU监控功能将被禁用")
            self.enabled = False
        
        # IndexTTS2模型预估显存需求（GB）
        self.model_memory_per_worker_gb = 8.0  # 每个worker预估需要8GB显存
        
        self.logger.info(f"GPU监控器初始化完成 - 启用: {self.enabled}, CUDA可用: {self.cuda_available}")
    
    def get_gpu_memory_info(self) -> Dict[str, float]:
        """
        获取GPU显存信息
        
        Returns:
            包含显存信息的字典
        """
        if not self.enabled or not self.cuda_available:
            return {
                'total_gb': 0.0,
                'used_gb': 0.0,
                'free_gb': 0.0,
                'usage_percent': 0.0
            }
        
        try:
            # 获取显存信息（字节）
            total_bytes = torch.cuda.get_device_properties(0).total_memory
            allocated_bytes = torch.cuda.memory_allocated(0)
            cached_bytes = torch.cuda.memory_reserved(0)
            
            # 转换为GB
            total_gb = total_bytes / (1024**3)
            used_gb = allocated_bytes / (1024**3)
            cached_gb = cached_bytes / (1024**3)
            free_gb = total_gb - used_gb
            
            usage_percent = (used_gb / total_gb) * 100 if total_gb > 0 else 0
            
            return {
                'total_gb': total_gb,
                'used_gb': used_gb,
                'cached_gb': cached_gb,
                'free_gb': free_gb,
                'usage_percent': usage_percent
            }
        except Exception as e:
            self.logger.error(f"获取GPU显存信息失败: {e}")
            return {
                'total_gb': 0.0,
                'used_gb': 0.0,
                'free_gb': 0.0,
                'usage_percent': 0.0
            }
    
    def suggest_parallel_workers(self, max_workers: int = 4) -> int:
        """
        根据可用显存动态建议并行worker数量
        
        Args:
            max_workers: 最大worker数量限制
            
        Returns:
            建议的worker数量
        """
        if not self.enabled or not self.cuda_available:
            return 1
        
        try:
            memory_info = self.get_gpu_memory_info()
            free_memory = memory_info['free_gb']
            
            # 计算可用显存（减去安全边距）
            available_memory = free_memory - self.safety_margin_gb
            
            if available_memory <= 0:
                self.logger.warning(f"可用显存不足（{free_memory:.1f}GB），建议使用1个worker")
                return 1
            
            # 根据模型显存需求计算建议的worker数量
            suggested_workers = int(available_memory / self.model_memory_per_worker_gb)
            
            # 限制在合理范围内
            suggested_workers = max(1, min(suggested_workers, max_workers))
            
            self.logger.info(
                f"GPU显存建议: 可用{available_memory:.1f}GB, "
                f"建议{self.model_memory_per_worker_gb}GB/worker, "
                f"建议{suggested_workers}个worker"
            )
            
            return suggested_workers
            
        except Exception as e:
            self.logger.error(f"计算并行worker数量失败: {e}")
            return 1
    
    def clear_cache(self):
        """清理GPU缓存"""
        if not self.enabled or not self.cuda_available:
            return
        
        try:
            # 清理PyTorch CUDA缓存
            torch.cuda.empty_cache()
            
            # 强制垃圾回收
            gc.collect()
            
            self.logger.debug("GPU缓存已清理")
        except Exception as e:
            self.logger.error(f"清理GPU缓存失败: {e}")
    
    def log_memory_status(self, context: str = ""):
        """
        记录显存状态到日志
        
        Args:
            context: 上下文信息，用于标识日志来源
        """
        if not self.enabled or not self.cuda_available:
            return
        
        try:
            memory_info = self.get_gpu_memory_info()
            
            context_str = f" [{context}]" if context else ""
            self.logger.info(
                f"GPU显存状态{context_str}: "
                f"总计{memory_info['total_gb']:.1f}GB, "
                f"已用{memory_info['used_gb']:.1f}GB, "
                f"可用{memory_info['free_gb']:.1f}GB, "
                f"使用率{memory_info['usage_percent']:.1f}%"
            )
        except Exception as e:
            self.logger.error(f"记录GPU显存状态失败: {e}")
    
    def get_device_info(self) -> Dict[str, Any]:
        """
        获取GPU设备信息
        
        Returns:
            设备信息字典
        """
        if not self.enabled or not self.cuda_available:
            return {'device_name': 'CPU', 'cuda_available': False}
        
        try:
            device_props = torch.cuda.get_device_properties(0)
            return {
                'device_name': device_props.name,
                'cuda_available': True,
                'compute_capability': f"{device_props.major}.{device_props.minor}",
                'total_memory_gb': device_props.total_memory / (1024**3),
                'multiprocessor_count': device_props.multi_processor_count
            }
        except Exception as e:
            self.logger.error(f"获取GPU设备信息失败: {e}")
            return {'device_name': 'Unknown', 'cuda_available': False}