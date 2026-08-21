"""
初始化/配置相关 API：
- GET  /api/setup/status  判断 LLM 三件套是否已配置（前端路由守卫使用）
- POST /api/setup/apply   接收前端表单，写入 .env 并可选重启 supervisord
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter(tags=["setup"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
MANAGE_SCRIPT = PROJECT_ROOT / "manage-supervisor.sh"

MIRROR_VARS: List[str] = [
    "MIRROR_MODE",
    "HF_ENDPOINT",
    "USE_MODELSCOPE",
    "UV_DEFAULT_INDEX",
    "NPM_REGISTRY",
    "NODE_SETUP_URL",
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "UV_HTTP_TIMEOUT",
]

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _parse_env() -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not ENV_FILE.is_file():
        return env
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        env[k] = v
    return env


def _is_configured() -> bool:
    env = _parse_env()
    base = (env.get("LLM_BASE_URL") or "").strip()
    key = (env.get("LLM_API_KEY") or "").strip()
    model = (env.get("LLM_MODEL") or "").strip()
    if base and key and model:
        return True
    dashscope = (env.get("DASHSCOPE_API_KEY") or "").strip()
    if dashscope:  # 兜底：旧配置也算配置过
        return True
    return False


@router.get("/setup/status")
def get_setup_status() -> Dict[str, Any]:
    """返回是否已配置 LLM；若已配置，脱敏返回当前配置概览。"""
    env = _parse_env()
    configured = _is_configured()
    base = (env.get("LLM_BASE_URL") or "").strip()
    model = (env.get("LLM_MODEL") or "").strip()
    key = (env.get("LLM_API_KEY") or "").strip()
    key_masked = ""
    if key:
        if len(key) <= 8:
            key_masked = "***"
        else:
            key_masked = f"{key[:4]}…{key[-4:]}"
    return {
        "configured": configured,
        "env_file_exists": ENV_FILE.is_file(),
        "current": {
            "llm_base_url": base if configured else "",
            "llm_model": model if configured else "",
            "llm_api_key_masked": key_masked if configured else "",
            "llm_temperature": env.get("LLM_TEMPERATURE", "") if configured else "",
            "llm_timeout": env.get("LLM_TIMEOUT", "") if configured else "",
        },
    }


class SetupApplyRequest(BaseModel):
    llm_base_url: str = Field(..., min_length=1, description="OpenAI compatible base URL，必须 http(s) 开头")
    llm_api_key: str = Field(..., min_length=1, description="API Key；本地无鉴权填 EMPTY")
    llm_model: str = Field(..., min_length=1, description="模型名")
    llm_temperature: str | None = Field(default=None, description="采样温度，留空走代码默认")
    llm_timeout: str | None = Field(default=None, description="单次请求超时秒数，留空走代码默认")
    restart: bool = Field(default=True, description="写入后是否立即重启服务")

    @field_validator("llm_base_url")
    @classmethod
    def _v_url(cls, v: str) -> str:
        v = v.strip()
        if not _URL_RE.match(v):
            raise ValueError("llm_base_url 必须以 http:// 或 https:// 开头")
        return v

    @field_validator("llm_api_key", "llm_model")
    @classmethod
    def _v_nonempty_strip(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("不能为空")
        return s

    @field_validator("llm_temperature")
    @classmethod
    def _v_temp(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        try:
            f = float(s)
        except (TypeError, ValueError) as e:
            raise ValueError("llm_temperature 必须是数字") from e
        if not 0.0 <= f <= 2.0:
            raise ValueError("llm_temperature 范围 0.0 ~ 2.0")
        return s

    @field_validator("llm_timeout")
    @classmethod
    def _v_timeout(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        if not re.fullmatch(r"[1-9][0-9]*", s):
            raise ValueError("llm_timeout 必须是正整数")
        return s


def _render_env(req: SetupApplyRequest) -> str:
    old = _parse_env()
    lines: List[str] = []
    lines.append("# 复制本文件为 .env（HAI 镜像用户已自动备好）")
    lines.append("# 详细配置说明：docs/ENV_ADVANCED.md")
    lines.append("")
    lines.append("# 必填：OpenAI 兼容 LLM 配置（/v1/chat/completions）")
    lines.append(f"LLM_BASE_URL={req.llm_base_url}")
    lines.append(f"LLM_API_KEY={req.llm_api_key}")
    lines.append(f"LLM_MODEL={req.llm_model}")
    lines.append("")
    lines.append("# 可选：LLM 调优参数（留空走代码默认值）")
    if req.llm_temperature:
        lines.append(f"LLM_TEMPERATURE={req.llm_temperature}")
    else:
        lines.append("# LLM_TEMPERATURE=0.1")
    if req.llm_timeout:
        lines.append(f"LLM_TIMEOUT={req.llm_timeout}")
    else:
        lines.append("# LLM_TIMEOUT=300")
    lines.append("")
    lines.append("# HAI 镜像专用（无需修改）")

    written = set()
    # 优先写回镜像相关变量
    for k in ["MIRROR_MODE", "HF_ENDPOINT", "USE_MODELSCOPE"]:
        if k in old and old[k]:
            lines.append(f"{k}={old[k]}")
            written.add(k)
    for k in ["UV_DEFAULT_INDEX", "NPM_REGISTRY", "NODE_SETUP_URL", "UV_HTTP_TIMEOUT"]:
        if k in old and old[k]:
            lines.append(f"{k}={old[k]}")
            written.add(k)
    # 离线模式相关（保留注释形式，以注释或原值
    for k in ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"]:
        if k in old and old[k]:
            lines.append(f"# {k}={old[k]}")
            written.add(k)
    # 兜底默认值
    if "MIRROR_MODE" not in written:
        lines.append("MIRROR_MODE=tencent-intranet")
    if "HF_ENDPOINT" not in written:
        lines.append("HF_ENDPOINT=https://hf-mirror.com")
    if "USE_MODELSCOPE" not in written:
        lines.append("USE_MODELSCOPE=true")
    lines.append("")
    return "\n".join(lines) + "\n"


def _restart_supervisor() -> Dict[str, Any]:
    if not MANAGE_SCRIPT.is_file() or not os.access(MANAGE_SCRIPT, os.X_OK):
        return {"restarted": False, "message": "manage-supervisor.sh 不存在或不可执行，跳过重启", "code": None}
    try:
        proc = subprocess.run(
            [str(MANAGE_SCRIPT), "restart"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        tail = "\n".join(proc.stdout.strip().splitlines()[-8:])
        if proc.returncode == 0:
            return {"restarted": True, "message": tail or "服务已重启", "code": 0}
        err = "\n".join(proc.stderr.strip().splitlines()[-4:])
        msg_parts = []
        if tail:
            msg_parts.append(tail)
        if err:
            msg_parts.append(err)
        message = ("\n".join(msg_parts) if msg_parts else f"返回码 {proc.returncode}")
        return {
            "restarted": False,
            "message": message,
            "code": proc.returncode,
        }
    except subprocess.TimeoutExpired as e:
        return {"restarted": False, "message": f"重启超时（>600s）：{e}", "code": -1}
    except Exception as e:  # pragma: no cover
        return {"restarted": False, "message": f"重启失败：{e}", "code": -2}


@router.post("/setup/apply")
def apply_setup(req: SetupApplyRequest) -> Dict[str, Any]:
    """写入 .env 并可选重启服务。"""
    # 保证项目根目录可写
    if not PROJECT_ROOT.exists():
        raise HTTPException(status_code=500, detail=f"项目根目录不存在: {PROJECT_ROOT}")
    if not os.access(PROJECT_ROOT, os.W_OK):
        raise HTTPException(status_code=500, detail=f"项目根目录不可写，无法写入 .env")

    content = _render_env(req)
    # 先写入临时文件，再原子替换，防止半写导致损坏
    fd, tmp_path = tempfile.mkstemp(prefix=".env.", dir=str(PROJECT_ROOT))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, ENV_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    result: Dict[str, Any] = {
        "saved": True,
        "env_file": str(ENV_FILE),
        "restart": req.restart,
    }
    if req.restart:
        result["restart_result"] = _restart_supervisor()
    else:
        result["restart_result"] = {"restarted": False, "message": "用户跳过重启，需手动执行 ./manage-supervisor.sh restart", "code": None}
    return result
