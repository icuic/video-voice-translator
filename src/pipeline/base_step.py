"""
步骤基类
定义统一的步骤接口和通用逻辑
"""

import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from .processing_context import ProcessingContext


class BaseStep(ABC):
    """步骤基类 - 定义统一的步骤接口"""
    
    def __init__(self, context: ProcessingContext):
        """
        初始化步骤
        
        Args:
            context: 处理上下文
        """
        self.context = context
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = context.config
        self.output_manager = context.output_manager
        self.stats = context.stats
        self.task_dir = context.task_dir
    
    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """
        执行步骤
        
        Returns:
            步骤执行结果字典
        """
        pass
    
    def get_model(self, model_name: str):
        """
        获取预加载的模型（如果可用）
        
        Args:
            model_name: 模型名称
            
        Returns:
            模型实例或None
        """
        try:
            # 检查预加载状态
            preloader_available = False
            try:
                if os.path.exists('/tmp/voice_clone_preloader_available'):
                    with open('/tmp/voice_clone_preloader_available', 'r') as f:
                        content = f.read().strip()
                        preloader_available = content == 'true'
            except Exception:
                pass
            
            if preloader_available:
                from ..model_preloader import ModelPreloader
                preloader = ModelPreloader.get_instance()
                if preloader.is_model_loaded(model_name):
                    self.logger.info(f"🚀 使用预加载的模型: {model_name}")
                    return preloader.get_loaded_model(model_name)
        except Exception as e:
            self.logger.warning(f"预加载模型获取失败: {e}")
        
        return None
    
    def read_file(self, filename: str) -> str:
        """
        从任务目录读取文件
        
        Args:
            filename: 文件名
            
        Returns:
            文件内容
        """
        file_path = os.path.join(self.task_dir, filename)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def read_json(self, filename: str) -> Dict[str, Any]:
        """
        从任务目录读取JSON文件
        
        Args:
            filename: 文件名
            
        Returns:
            JSON数据字典
        """
        import json
        file_path = os.path.join(self.task_dir, filename)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def write_json(self, filename: str, data: Dict[str, Any]) -> str:
        """
        写入JSON文件到任务目录
        
        Args:
            filename: 文件名
            data: 数据字典
            
        Returns:
            文件路径
        """
        import json
        file_path = os.path.join(self.task_dir, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return file_path
    
    def file_exists(self, filename: str) -> bool:
        """
        检查文件是否存在
        
        Args:
            filename: 文件名
            
        Returns:
            文件是否存在
        """
        file_path = os.path.join(self.task_dir, filename)
        return os.path.exists(file_path)
    
    def log_step_start(self, step_name: str):
        """记录步骤开始"""
        self.logger.info(f"开始执行: {step_name}")
        self.output_manager.log(f"步骤开始: {step_name}")
        self.stats.start_step(step_name.lower().replace(' ', '_'))
    
    def log_step_end(self, step_name: str, result: Dict[str, Any], elapsed_time: float):
        """记录步骤结束"""
        status = 'success' if result.get("success", False) else 'failed'
        self.logger.info(f"步骤完成: {step_name} - {status} (耗时: {elapsed_time:.1f}秒)")
        self.output_manager.log(f"步骤完成: {step_name} - {status} (耗时: {elapsed_time:.1f}秒)")
        self.stats.end_step(step_name.lower().replace(' ', '_'), result)
    
    def run_with_stats(self, step_name: str) -> Dict[str, Any]:
        """
        运行步骤并记录统计信息
        
        Args:
            step_name: 步骤名称
            
        Returns:
            步骤执行结果
        """
        self.log_step_start(step_name)
        start_time = time.time()
        
        try:
            result = self.execute()
            elapsed_time = time.time() - start_time
            self.log_step_end(step_name, result, elapsed_time)
            return result
        except Exception as e:
            elapsed_time = time.time() - start_time
            error_result = {
                "success": False,
                "error": str(e)
            }
            self.log_step_end(step_name, error_result, elapsed_time)
            self.logger.error(f"步骤执行失败: {e}", exc_info=True)
            raise

