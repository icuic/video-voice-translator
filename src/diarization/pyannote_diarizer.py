"""
基于 pyannote.audio 的说话人切分封装
返回统一的时间线: [{start, end, speaker_id, confidence}]
"""

import os
import logging
from typing import List, Dict, Any, Optional
import torch


class PyannoteDiarizer:
    """轻量封装 pyannote.audio 说话人切分"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)

        diar_cfg = config.get("speaker_diarization", {})
        self.enabled: bool = diar_cfg.get("enabled", True)
        self.model_name: str = diar_cfg.get("model", "pyannote/speaker-diarization-3.1")
        self.device: str = diar_cfg.get("device", "cpu")
        self.min_speakers: Optional[int] = diar_cfg.get("min_speakers", None)
        self.max_speakers: Optional[int] = diar_cfg.get("max_speakers", None)

        self._pipeline = None
        if self.enabled:
            self._init_pipeline()

    def _init_pipeline(self):
        try:
            from pyannote.audio import Pipeline
            hf_token = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
            if hf_token:
                self._pipeline = Pipeline.from_pretrained(self.model_name, use_auth_token=hf_token)
            else:
                self._pipeline = Pipeline.from_pretrained(self.model_name)

            # 移动到目标设备（将字符串转换为 torch.device）
            try:
                target_device = torch.device(self.device if isinstance(self.device, str) else str(self.device))
            except Exception:
                target_device = torch.device("cpu")
            self._pipeline.to(target_device)

            self.logger.info(f"pyannote.pipeline 加载成功: {self.model_name} @ {target_device}")
        except Exception as e:
            self.logger.warning(f"pyannote 加载失败，自动禁用说话人切分: {e}")
            self.enabled = False

    def diarize(self, audio_path: str) -> List[Dict[str, Any]]:
        """对整段音频进行说话人切分，输出统一格式列表"""
        if not self.enabled or self._pipeline is None:
            self.logger.info("说话人切分未启用或不可用，返回空列表")
            return []

        try:
            params = {}
            if self.min_speakers is not None:
                params["min_speakers"] = int(self.min_speakers)
            if self.max_speakers is not None:
                params["max_speakers"] = int(self.max_speakers)

            diarization = self._pipeline(audio_path, **params)

            results: List[Dict[str, Any]] = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                # pyannote 3.1 提供 score 需要额外处理；这里置为 1.0 作为占位
                results.append({
                    "start": float(turn.start),
                    "end": float(turn.end),
                    "speaker_id": str(speaker),
                    "confidence": 1.0
                })

            # 按时间排序
            results.sort(key=lambda x: (x["start"], x["end"]))
            self.logger.info(f"diarization 完成: {len(results)} 段")
            return results
        except Exception as e:
            self.logger.warning(f"diarization 失败，返回空列表: {e}")
            return []


