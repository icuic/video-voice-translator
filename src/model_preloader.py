"""
模型预加载器模块
负责在系统启动时预加载所有必要的模型，提升处理速度
"""

import os
import sys
import time
import shutil
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from .utils import load_config

class ModelPreloader:
    """模型预加载器类"""
    
    # 类级单例变量
    _instance = None
    _initialized = False
    
    def __new__(cls, config_path: str = "config.yaml"):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super(ModelPreloader, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls, config_path: str = "config.yaml"):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化模型预加载器
        
        Args:
            config_path: 配置文件路径
        """
        # 避免重复初始化
        if self._initialized:
            return
            
        self.config = load_config(config_path)
        self.logger = logging.getLogger(__name__)
        
        # 模型状态跟踪
        self.model_status = {
            "IndexTTS2": {"status": "未加载", "progress": 0, "error": None},
            "Whisper": {"status": "未加载", "progress": 0, "error": None},
            "AudioSeparator": {"status": "未加载", "progress": 0, "error": None},
            "TextTranslator": {"status": "未加载", "progress": 0, "error": None},
            "SpeakerDiarizer": {"status": "未加载", "progress": 0, "error": None}
        }
        
        # 预加载的模型实例
        self.loaded_models = {}
        
        self._initialized = True
        self.logger.info("模型预加载器初始化完成")
    
    def preload_all_models(self, async_loading: bool = True) -> bool:
        """
        预加载所有模型
        
        Args:
            async_loading: 是否异步加载
            
        Returns:
            是否全部加载成功
        """
        self.logger.info("🚀 开始预加载所有模型...")
        
        if async_loading:
            # 异步加载
            threads = []
            for model_name in self.model_status.keys():
                thread = threading.Thread(
                    target=self._preload_single_model,
                    args=(model_name,),
                    name=f"Preload-{model_name}"
                )
                thread.start()
                threads.append(thread)
            
            # 等待所有线程完成
            for thread in threads:
                thread.join()
        else:
            # 同步加载
            for model_name in self.model_status.keys():
                self._preload_single_model(model_name)
        
        # 检查加载结果
        success_count = sum(1 for status in self.model_status.values() 
                          if status["status"] == "已加载")
        total_count = len(self.model_status)
        
        self.logger.info(f"模型预加载完成: {success_count}/{total_count} 成功")
        return success_count == total_count
    
    def _preload_single_model(self, model_name: str):
        """预加载单个模型"""
        try:
            self.model_status[model_name]["status"] = "加载中..."
            self.model_status[model_name]["progress"] = 10
            
            if model_name == "IndexTTS2":
                self._preload_indexTTS2()
            elif model_name == "Whisper":
                self._preload_whisper()
            elif model_name == "AudioSeparator":
                self._preload_audio_separator()
            elif model_name == "TextTranslator":
                self._preload_text_translator()
            elif model_name == "SpeakerDiarizer":
                self._preload_speaker_diarizer()
            
            self.model_status[model_name]["status"] = "已加载"
            self.model_status[model_name]["progress"] = 100
            self.logger.info(f"✅ {model_name} 模型预加载完成")
            
        except Exception as e:
            self.model_status[model_name]["status"] = "加载失败"
            self.model_status[model_name]["error"] = str(e)
            self.logger.error(f"❌ {model_name} 模型预加载失败: {e}")
    
    def _sanitize_indext2_hf_cache(self) -> None:
        """
        在调用第三方 IndexTTS2 之前，对 checkpoints/hf_cache/ 做完整性检查，
        遇到下载中断留下的空壳半成品目录/文件时提前清理掉，
        迫使第三方 ensure_models_available 重新下载完整副本。
        全程不修改任何第三方 index-tts 子模块代码。
        """
        src_dir = Path(__file__).resolve().parent.parent
        hf_cache = src_dir / "index-tts" / "checkpoints" / "hf_cache"
        if not hf_cache.is_dir():
            return

        w2v_dir = hf_cache / "w2v-bert-2.0"
        w2v_marker = w2v_dir / "preprocessor_config.json"
        w2v_model = w2v_dir / "model.safetensors"
        if w2v_dir.is_dir():
            if not w2v_marker.is_file() or not w2v_model.is_file() or w2v_model.stat().st_size < 100 * 1024 * 1024:
                self.logger.warning(
                    f"🧹 w2v-bert-2.0 目录存在但关键文件缺失/不完整（仅 {w2v_model.stat().st_size if w2v_model.is_file() else 0} 字节），"
                    f"清理半成品目录: {w2v_dir}"
                )
                shutil.rmtree(w2v_dir, ignore_errors=True)
                bad_hub_cache = src_dir / "index-tts" / ".cache" / "hf" / "hub" / "models--facebook--w2v-bert-2.0"
                if bad_hub_cache.is_dir():
                    shutil.rmtree(bad_hub_cache, ignore_errors=True)

        sem_file = hf_cache / "semantic_codec_model.safetensors"
        if sem_file.exists():
            if sem_file.stat().st_size < 100 * 1024 * 1024:
                self.logger.warning(f"🧹 semantic_codec_model.safetensors 仅 {sem_file.stat().st_size} 字节，清理半成品")
                sem_file.unlink(missing_ok=True)
        sem_dir = hf_cache / "semantic_codec"
        sem_inner = sem_dir / "model.safetensors"
        if sem_dir.is_dir():
            if not sem_inner.is_file() or sem_inner.stat().st_size < 100 * 1024 * 1024:
                self.logger.warning(f"🧹 semantic_codec/ 目录不完整，清理半成品: {sem_dir}")
                shutil.rmtree(sem_dir, ignore_errors=True)

        camp_file = hf_cache / "campplus_cn_common.bin"
        if camp_file.exists() and camp_file.stat().st_size < 10 * 1024 * 1024:
            self.logger.warning(f"🧹 campplus_cn_common.bin 仅 {camp_file.stat().st_size} 字节，清理半成品")
            camp_file.unlink(missing_ok=True)

        bigvgan_dir = hf_cache / "bigvgan"
        bigv_cfg = bigvgan_dir / "config.json"
        bigv_pt = bigvgan_dir / "bigvgan_generator.pt"
        if bigvgan_dir.is_dir():
            if not bigv_cfg.is_file() or not bigv_pt.is_file() or bigv_pt.stat().st_size < 100 * 1024 * 1024:
                self.logger.warning(
                    f"🧹 bigvgan/ 目录不完整（pt={bigv_pt.stat().st_size if bigv_pt.is_file() else 0} 字节），"
                    f"清理半成品: {bigvgan_dir}"
                )
                shutil.rmtree(bigvgan_dir, ignore_errors=True)

    def _preload_indexTTS2(self):
        """预加载 IndexTTS2 模型"""
        try:
            self._sanitize_indext2_hf_cache()
            from .voice_cloner import VoiceCloner
            voice_cloner = VoiceCloner(self.config)
            self.loaded_models["IndexTTS2"] = voice_cloner
            self.logger.info("IndexTTS2 模型预加载成功")
        except Exception as e:
            raise Exception(f"IndexTTS2 预加载失败: {e}")
    
    def _preload_whisper(self):
        """预加载 Whisper 模型"""
        try:
            from .whisper_processor import WhisperProcessor
            whisper_processor = WhisperProcessor(self.config)
            self.loaded_models["Whisper"] = whisper_processor
            self.logger.info("Whisper 模型预加载成功")
        except Exception as e:
            raise Exception(f"Whisper 预加载失败: {e}")
    
    def _preload_audio_separator(self):
        """预加载音频分离器"""
        try:
            from .audio_separator import AudioSeparator
            audio_separator = AudioSeparator(self.config)
            self.loaded_models["AudioSeparator"] = audio_separator
            self.logger.info("音频分离器预加载成功")
        except Exception as e:
            raise Exception(f"音频分离器预加载失败: {e}")
    
    def _preload_text_translator(self):
        """预加载文本翻译器"""
        try:
            from .text_translator import TextTranslator
            text_translator = TextTranslator(self.config)
            self.loaded_models["TextTranslator"] = text_translator
            self.logger.info("文本翻译器预加载成功")
        except Exception as e:
            raise Exception(f"文本翻译器预加载失败: {e}")
    
    def _preload_speaker_diarizer(self):
        """预加载说话人分离器"""
        try:
            from .speaker_diarizer import SpeakerDiarizer
            speaker_diarizer = SpeakerDiarizer(self.config)
            self.loaded_models["SpeakerDiarizer"] = speaker_diarizer
            self.logger.info("说话人分离器预加载成功")
        except Exception as e:
            raise Exception(f"说话人分离器预加载失败: {e}")
    
    def get_model_status(self) -> Dict[str, Any]:
        """获取模型状态"""
        return self.model_status.copy()
    
    def get_model_statuses(self) -> Dict[str, Dict[str, Any]]:
        """获取所有模型状态的详细信息"""
        return self.model_status.copy()
    
    def get_model_status_text(self) -> str:
        """获取模型状态文本"""
        status_text = "📊 模型加载状态:\n\n"
        
        for model_name, status in self.model_status.items():
            progress_bar = "█" * (status["progress"] // 10) + "░" * (10 - status["progress"] // 10)
            status_icon = "✅" if status["status"] == "已加载" else "❌" if status["status"] == "加载失败" else "⏳"
            status_text += f"{status_icon} {model_name}: {status['status']} {progress_bar} {status['progress']}%\n"
            
            if status["error"]:
                status_text += f"   └─ 错误: {status['error']}\n"
        
        return status_text
    
    def get_loaded_model(self, model_name: str) -> Optional[Any]:
        """获取已加载的模型实例"""
        print(f"🔍 尝试获取模型: {model_name}")
        print(f"🔍 已加载的模型: {list(self.loaded_models.keys())}")
        print(f"🔍 模型状态: {self.model_status.get(model_name, 'Unknown')}")
        
        model = self.loaded_models.get(model_name)
        if model:
            print(f"✅ 成功获取模型: {model_name}")
        else:
            print(f"❌ 模型 {model_name} 未找到")
        return model
    
    def is_model_loaded(self, model_name: str) -> bool:
        """检查模型是否已加载"""
        return (model_name in self.loaded_models and 
                self.model_status[model_name]["status"] == "已加载")
    
    def get_loading_progress(self) -> float:
        """获取总体加载进度"""
        total_progress = sum(status["progress"] for status in self.model_status.values())
        return total_progress / len(self.model_status)
    
    def get_successful_models(self) -> List[str]:
        """获取成功加载的模型列表"""
        return [name for name, status in self.model_status.items() 
                if status["status"] == "已加载"]
    
    def get_failed_models(self) -> List[str]:
        """获取加载失败的模型列表"""
        return [name for name, status in self.model_status.items() 
                if status["status"] == "加载失败"]
