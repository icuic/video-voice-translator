"""
目标说话人提取（TSE）实现：
基于 ECAPA 说话人嵌入与频域相似度掩膜，对重叠片段进行目标增强。
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np


class TargetSpeakerEnhancer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        tse_cfg = (config.get("speaker_tracks", {}) or {}).get("tse", {}) or {}
        self.frame_ms: int = int(tse_cfg.get("frame_ms", 25))
        self.hop_ms: int = int(tse_cfg.get("hop_ms", 10))
        self.temperature: float = float(tse_cfg.get("temperature", 3.0))
        self.threshold: float = float(tse_cfg.get("threshold", 0.2))
        self.smoothing_ms: int = int(tse_cfg.get("smoothing_ms", 50))
        self.min_gain_db: float = float(tse_cfg.get("min_gain_db", -18.0))

        # 说话人嵌入缓存: speaker_id -> np.ndarray(embedding)
        self._speaker_embed: Dict[str, np.ndarray] = {}

        # 懒加载 speechbrain ECAPA 模型
        self._ecapa = None

        # 最近一次掩膜统计
        self.last_mask_stats: Dict[str, float] = {}

    def _lazy_load_ecapa(self):
        if self._ecapa is None:
            from speechbrain.pretrained import EncoderClassifier
            # 使用默认 CPU/GPU 由 torch 自动选择
            self._ecapa = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir="/tmp/speechbrain_ecapa"
            )

    def _extract_embed(self, wav: np.ndarray, sr: int) -> np.ndarray:
        """提取全局说话人嵌入，输入单声道波形。"""
        self._lazy_load_ecapa()
        # speechbrain 期望形状: [batch, time]
        import torch
        with torch.no_grad():
            tensor = torch.from_numpy(wav.astype(np.float32)).unsqueeze(0)
            emb = self._ecapa.encode_batch(tensor)
            emb = emb.squeeze(0).squeeze(0).cpu().numpy()
        # 归一化
        norm = np.linalg.norm(emb) + 1e-9
        return emb / norm

    def _get_target_embed(self, speaker_id: str, init_wav: np.ndarray, sr: int) -> np.ndarray:
        """获取/缓存目标说话人嵌入。首次调用用当前片段的中心1~3秒估计。"""
        if speaker_id in self._speaker_embed:
            return self._speaker_embed[speaker_id]
        # 取中间最多3秒构建初始嵌入
        total = len(init_wav)
        dur = total / max(sr, 1)
        want = min(3.0, max(1.0, dur))
        center = total // 2
        half = int(want * sr / 2)
        s = max(0, center - half)
        e = min(total, center + half)
        ref = init_wav[s:e]
        emb = self._extract_embed(ref, sr)
        self._speaker_embed[speaker_id] = emb
        return emb

    def _stft(self, wav: np.ndarray, sr: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        from scipy.signal import stft
        nperseg = max(256, int(self.frame_ms * sr / 1000))
        noverlap = max(0, int((self.frame_ms - self.hop_ms) * sr / 1000))
        f, t, Zxx = stft(wav, fs=sr, nperseg=nperseg, noverlap=noverlap, boundary=None)
        return f, t, Zxx

    def _istft(self, Zxx: np.ndarray, sr: int) -> np.ndarray:
        from scipy.signal import istft
        nperseg = Zxx.shape[0] * 2 - 2  # 由 STFT 反推 window 长度（近似）
        _, wav = istft(Zxx, fs=sr, nperseg=nperseg, input_onesided=True, boundary=None)
        return wav.astype(np.float32)

    def _build_mask(self, wav: np.ndarray, sr: int, target_emb: np.ndarray) -> np.ndarray:
        """基于滑窗嵌入与目标嵌入余弦相似度生成时间掩膜(0..1)。"""
        hop = max(1, int(self.hop_ms * sr / 1000))
        win = max(hop, int(self.frame_ms * sr / 1000))
        if len(wav) < win:
            emb = self._extract_embed(wav, sr)
            sim = float(np.dot(emb, target_emb))
            score = 1.0 / (1.0 + np.exp(-self.temperature * (sim - self.threshold)))
            return np.full(1, score, dtype=np.float32)

        scores = []
        pos = 0
        while pos < len(wav):
            chunk = wav[pos:pos + win]
            if len(chunk) < int(0.4 * win):
                break
            emb = self._extract_embed(chunk, sr)
            sim = float(np.dot(emb, target_emb))
            score = 1.0 / (1.0 + np.exp(-self.temperature * (sim - self.threshold)))
            scores.append(score)
            pos += hop
        if not scores:
            scores = [0.5]
        mask_t = np.array(scores, dtype=np.float32)
        # 平滑（移动平均）
        smooth_hops = max(1, int(self.smoothing_ms / max(self.hop_ms, 1)))
        if smooth_hops > 1:
            kernel = np.ones(smooth_hops, dtype=np.float32) / smooth_hops
            mask_t = np.convolve(mask_t, kernel, mode='same')
        return mask_t

    def enhance_chunk(self, audio_chunk: np.ndarray, sr: int, speaker_id: str) -> np.ndarray:
        """对给定片段做目标增强：频域乘性掩膜，抑制非目标说话人。"""
        if audio_chunk is None or len(audio_chunk) == 0:
            return audio_chunk
        target_emb = self._get_target_embed(speaker_id, audio_chunk, sr)
        f, t, Zxx = self._stft(audio_chunk, sr)
        mag = np.abs(Zxx)
        phase = np.angle(Zxx)

        # 时间掩膜构建与插值到 STFT 帧
        time_mask = self._build_mask(audio_chunk, sr, target_emb)  # 长度 ~ 帧数
        if len(time_mask) != len(t):
            # 线性插值到 STFT 帧数
            x_old = np.linspace(0.0, 1.0, num=len(time_mask), dtype=np.float32)
            x_new = np.linspace(0.0, 1.0, num=len(t), dtype=np.float32)
            time_mask = np.interp(x_new, x_old, time_mask).astype(np.float32)

        # 频率维均匀应用（简化版），并设定最小增益
        min_gain = 10 ** (self.min_gain_db / 20.0)
        mask_2d = np.clip(time_mask[None, :], min_gain, 1.0)

        masked_mag = mag * mask_2d
        Zxx_new = masked_mag * np.exp(1j * phase)
        enhanced = self._istft(Zxx_new, sr)

        # 对齐长度
        if len(enhanced) > len(audio_chunk):
            enhanced = enhanced[:len(audio_chunk)]
        elif len(enhanced) < len(audio_chunk):
            pad = np.zeros(len(audio_chunk) - len(enhanced), dtype=np.float32)
            enhanced = np.concatenate([enhanced, pad], axis=0)

        # 记录掩膜统计
        self.last_mask_stats = {
            "mask_mean": float(np.mean(time_mask)),
            "mask_std": float(np.std(time_mask)),
        }
        return enhanced


