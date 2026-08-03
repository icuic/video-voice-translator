"""
设备探测工具。

统一处理 NVIDIA CUDA、AMD ROCm 和 CPU 三类运行环境，避免各模块自行硬编码。
"""

from typing import Any, Dict, Optional


def get_torch_runtime_info() -> Dict[str, Any]:
    """返回当前 PyTorch 运行时的设备信息。"""
    info: Dict[str, Any] = {
        "torch_available": False,
        "gpu_available": False,
        "accelerator_kind": "cpu",
        "accelerator_label": "CPU",
        "device": "cpu",
        "device_name": "CPU",
    }

    try:
        import torch
    except ImportError:
        return info

    info["torch_available"] = True

    if not torch.cuda.is_available():
        return info

    info["gpu_available"] = True
    info["device"] = "cuda"

    hip_version = getattr(torch.version, "hip", None)
    cuda_version = getattr(torch.version, "cuda", None)

    if hip_version:
        info["accelerator_kind"] = "rocm"
        info["accelerator_label"] = "AMD ROCm"
    elif cuda_version:
        info["accelerator_kind"] = "cuda"
        info["accelerator_label"] = "NVIDIA CUDA"
    else:
        info["accelerator_kind"] = "gpu"
        info["accelerator_label"] = "GPU"

    try:
        info["device_name"] = torch.cuda.get_device_name(0)
    except Exception:
        pass

    return info


def get_preferred_torch_device(requested_device: str = "auto") -> str:
    """
    根据配置和当前运行时返回 PyTorch 应该使用的设备名。

    说明：ROCm 下 PyTorch 仍使用 `cuda` 作为设备字符串。
    """
    requested = (requested_device or "auto").lower()
    runtime_info = get_torch_runtime_info()

    if requested == "cpu":
        return "cpu"

    if requested in {"auto", "cuda"} and runtime_info["gpu_available"]:
        return "cuda"

    return "cpu"


def get_ctranslate2_gpu_available() -> bool:
    """
    判断 CTranslate2 是否检测到了可用 GPU。

    Faster-Whisper 依赖 CTranslate2，因此需要单独判断，而不是只看 torch.cuda。
    """
    try:
        import ctranslate2
    except ImportError:
        return False

    device_counter = getattr(ctranslate2, "get_cuda_device_count", None)
    if not callable(device_counter):
        return False

    try:
        return device_counter() > 0
    except Exception:
        return False


def should_enable_indextts_cuda_kernel(config_value: Optional[bool] = None) -> bool:
    """
    是否启用 IndexTTS2 的 CUDA kernel。

    如果用户显式配置，则尊重配置；否则仅在 NVIDIA CUDA 环境中启用，
    避免在 AMD/ROCm 环境中误开导致初始化失败。
    """
    if isinstance(config_value, bool):
        return config_value

    runtime_info = get_torch_runtime_info()
    return runtime_info["accelerator_kind"] == "cuda"


def is_gpu_runtime_error(error_msg: str) -> bool:
    """判断错误信息是否属于 GPU/CUDA/HIP 运行时错误。"""
    normalized = (error_msg or "").lower()
    keywords = (
        "cuda error",
        "hip error",
        "device-side assert",
        "hipruntime",
    )
    return any(keyword in normalized for keyword in keywords)
