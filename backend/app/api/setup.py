"""
初始化/配置相关 API：
- GET  /api/setup/status  判断 LLM 三件套是否已配置（前端路由守卫使用）
- POST /api/setup/apply   接收前端表单，写入 .env 并可选重启 supervisord
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter(tags=["setup"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
MANAGE_SCRIPT = PROJECT_ROOT / "manage-supervisor.sh"

# 结构记忆：parents 索引层级
# Path(".../backend/app/api/setup.py").resolve()
#   parents[0] = backend/app/api
#   parents[1] = backend/app
#   parents[2] = backend
#   parents[3] = 项目根（video-voice-translator/）✅
# 手动确认：
assert (PROJECT_ROOT / "manage-supervisor.sh").is_file(), (
    f"PROJECT_ROOT 算错！当前 PROJECT_ROOT={PROJECT_ROOT}，找不到 manage-supervisor.sh"
)
assert (PROJECT_ROOT / ".env.example").is_file(), (
    f"PROJECT_ROOT 算错！找不到 .env.example 在 {PROJECT_ROOT}"
)

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


def _normalize_env_value(v: Any) -> str:
    """规范化 .env 写入的 value：

    - 空值返回空字符串；
    - 字符串两端空白剥离；
    - 两端都是同一种引号（"..." / '...' / 误写的反引号 `...`）时统一剥离引号，
      避免 shell 加载阶段出现命令替换/变量展开的副作用；
    - 其他情况原样返回字符串形式。
    """
    if v is None:
        return ""
    s = str(v).strip()
    if len(s) >= 2:
        ends = (s[0], s[-1])
        if ends in (('"', '"'), ("'", "'"), ("`", "`")):
            s = s[1:-1].strip()
    return s


def _render_env(req: SetupApplyRequest) -> str:
    old = _parse_env()
    lines: List[str] = []
    lines.append("# 复制本文件为 .env（HAI 镜像用户已自动备好）")
    lines.append("# 详细配置说明：docs/ENV_ADVANCED.md")
    lines.append("")
    lines.append("# 必填：OpenAI 兼容 LLM 配置（/v1/chat/completions）")
    llm_base_url = _normalize_env_value(req.llm_base_url)
    llm_api_key = _normalize_env_value(req.llm_api_key)
    llm_model = _normalize_env_value(req.llm_model)
    llm_temperature = _normalize_env_value(req.llm_temperature) if req.llm_temperature else ""
    llm_timeout = _normalize_env_value(req.llm_timeout) if req.llm_timeout else ""
    lines.append(f"LLM_BASE_URL={llm_base_url}")
    lines.append(f"LLM_API_KEY={llm_api_key}")
    lines.append(f"LLM_MODEL={llm_model}")
    lines.append("")
    lines.append("# 可选：LLM 调优参数（留空走代码默认值）")
    if llm_temperature:
        lines.append(f"LLM_TEMPERATURE={llm_temperature}")
    else:
        lines.append("# LLM_TEMPERATURE=0.1")
    if llm_timeout:
        lines.append(f"LLM_TIMEOUT={llm_timeout}")
    else:
        lines.append("# LLM_TIMEOUT=300")
    lines.append("")
    lines.append("# HAI 镜像专用（无需修改）")

    written = set()
    # 优先写回镜像相关变量
    for k in ["MIRROR_MODE", "HF_ENDPOINT", "USE_MODELSCOPE"]:
        if k in old and old[k]:
            lines.append(f"{k}={_normalize_env_value(old[k])}")
            written.add(k)
    for k in ["UV_DEFAULT_INDEX", "NPM_REGISTRY", "NODE_SETUP_URL", "UV_HTTP_TIMEOUT"]:
        if k in old and old[k]:
            lines.append(f"{k}={_normalize_env_value(old[k])}")
            written.add(k)
    # 离线模式相关（保留注释形式）
    for k in ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"]:
        if k in old and old[k]:
            lines.append(f"# {k}={_normalize_env_value(old[k])}")
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


def _schedule_restart_backend_later(delay_seconds: float = 1.5) -> None:
    """把后端重启"延迟+完全脱离当前 uvicorn 进程"地触发，防止自杀式重启竞态。

    根因（已由真实 HAI 日志证实）：
      旧代码在 POST /setup/apply 的同步处理中直接调用 `manage-supervisor.sh restart-backend`，
      而这个 HTTP 请求本身就跑在 vvt-backend(uvicorn) 进程里面 → supervisorctl stop 一执行，
      会给当前 uvicorn 发 SIGTERM → 承载 subprocess.run 的 Python 进程 + 它 fork 出来的 bash /
      supervisorctl 一起被杀 → supervisorctl 的 restart 流程只执行到"stop"阶段，"start"阶段没
      跑完就挂了 → 日志里出现 stopped: vvt-backend 之后再也没有 spawned: vvt-backend → 服务永久 STOPPED。

    修复方式（两层保活，确保不会被一起带死）：
      1. 先返回 HTTP 200 给前端；
      2. 由守护线程 sleep 1.5s，保证响应 flush 完成、当前请求生命周期结束；
      3. 真正触发重启时：使用 nohup + shell `&` + subprocess.Popen(start_new_session=True, close_fds=True)，
         让重启脚本成为 init(1) 收养的孤儿进程，和当前 uvicorn 父子关系完全切断；
      4. 日志落到 data/logs/supervisor/restart-trigger.log，方便查"为什么没触发/触发在什么时候"。
    """
    import threading

    trigger_log = f"{PROJECT_ROOT}/data/logs/supervisor/restart-trigger.log"

    def _runner() -> None:
        import time

        try:
            time.sleep(max(0.0, float(delay_seconds)))
        except Exception:
            pass

        cmd = (
            f"cd {shlex.quote(str(PROJECT_ROOT))} && "
            f"nohup bash -lc {shlex.quote(f'{str(MANAGE_SCRIPT)} restart-backend')} "
            f">> {shlex.quote(trigger_log)} 2>&1 </dev/null &"
        )
        try:
            # 关键：start_new_session=True + 不继承 std 管道 → 父进程被杀时，这个 shell/子进程完全不受影响
            subprocess.Popen(
                cmd,
                shell=True,
                cwd=str(PROJECT_ROOT),
                start_new_session=True,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:  # pragma: no cover
            try:
                Path(PROJECT_ROOT / "data" / "logs" / "supervisor").mkdir(parents=True, exist_ok=True)
                with open(trigger_log, "a", encoding="utf-8") as fh:
                    fh.write(f"[{__import__('datetime').datetime.now().isoformat(timespec='seconds')}] "
                             f"[setup-api] schedule restart Popen 失败: {type(e).__name__}: {e}\n")
            except Exception:
                pass


def _restart_supervisor() -> Dict[str, Any]:
    if not MANAGE_SCRIPT.is_file() or not os.access(MANAGE_SCRIPT, os.X_OK):
        return {"restarted": False, "message": "manage-supervisor.sh 不存在或不可执行，跳过重启", "code": None}
    # 关键：这里的"重启"不是立即在当前请求里同步执行，而是"排程 1.5 秒后异步执行"，
    # 执行主体通过 Popen(nohup + start_new_session) 完全脱离当前 uvicorn 进程，
    # 避免 supervisor stop 把启动脚本也一起杀掉，导致"只停不启"的 STOPPED 竞态。
    try:
        Path(PROJECT_ROOT / "data" / "logs" / "supervisor").mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    _schedule_restart_backend_later(delay_seconds=1.5)
    log_hint = (
        "\n[提示] 已排程后端重启，约 1.5~10 秒后生效；"
        "若超过 30 秒仍 STOPPED，请查看后端崩溃日志："
        f" tail -n 80 {PROJECT_ROOT}/data/logs/supervisor/backend.err.log"
        f" {PROJECT_ROOT}/data/logs/supervisor/restart-trigger.log"
    )
    return {"restarted": True, "message": ("后端服务已排程异步重启（不会阻塞当前请求）" + log_hint), "code": 0}


def _diagnose_write_error(env_path: Path, project_root: Path) -> str:
    """当 .env 写入失败时，返回对用户友好的诊断信息（用户名/UID/权限/父目录属主）。"""
    import getpass
    parts = []
    parts.append("无法写入 .env，请排查以下权限问题：")
    parts.append(f"  - 当前进程用户名: {getpass.getuser()}  UID: {os.getuid()}  GID: {os.getgid()}")
    parts.append(f"  - 目标文件: {env_path}")
    parts.append(f"  - 父目录: {project_root}")
    try:
        st = project_root.stat()
        import pwd, grp
        owner = pwd.getpwuid(st.st_uid).pw_name if st.st_uid < 65536 and __import__('pwd').getpwuid(st.st_uid) else str(st.st_uid)
        try: group = grp.getgrgid(st.st_gid).gr_name
        except Exception: group = str(st.st_gid)
        parts.append(f"  - 父目录权限: {oct(st.st_mode & 0o777)}  属主: {owner}:{group}")
    except Exception as e:
        parts.append(f"  - [stat 父目录失败] {e}")
    if env_path.exists():
        try:
            st = env_path.stat()
            import pwd, grp
            try: owner = pwd.getpwuid(st.st_uid).pw_name
            except Exception: owner = str(st.st_uid)
            try: group = grp.getgrgid(st.st_gid).gr_name
            except Exception: group = str(st.st_gid)
            parts.append(f"  - .env 已存在，权限: {oct(st.st_mode & 0o777)}  属主: {owner}:{group}")
            parts.append(f"  - 当前用户是否可写: {'是' if os.access(env_path, os.W_OK) else '否（关键！）'}")
        except Exception as e:
            parts.append(f"  - [stat .env 失败] {e}")
    else:
        parts.append(f"  - .env 尚未创建，父目录是否可写: {'是' if os.access(project_root, os.W_OK) else '否（关键！）'}")
    parts.append("")
    parts.append("常见修复方式：")
    parts.append("  - Docker 部署：在宿主机执行 `sudo chown -R 999:999 /home/ubuntu/video-voice-translator/vvt-env /home/ubuntu/video-voice-translator/vvt-data`")
    parts.append("  - 源码部署：在项目根执行 `sudo chown -R $(whoami):$(whoami) . && chmod u+w . .env 2>/dev/null || true`")
    return "\n".join(parts)

@router.post("/setup/apply")
def apply_setup(req: SetupApplyRequest) -> Dict[str, Any]:
    """写入 .env 并可选重启服务。"""
    # 保证项目根目录可写
    if not PROJECT_ROOT.exists():
        raise HTTPException(status_code=500, detail=f"项目根目录不存在: {PROJECT_ROOT}")
    if not os.access(PROJECT_ROOT, os.W_OK):
        raise HTTPException(status_code=500, detail=_diagnose_write_error(ENV_FILE, PROJECT_ROOT))

    content = _render_env(req)
    # 先写入临时文件，再原子替换，防止半写导致损坏
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=".env.", dir=str(PROJECT_ROOT))
    except Exception as e:
        raise HTTPException(status_code=500, detail=_diagnose_write_error(ENV_FILE, PROJECT_ROOT) + f"\n[创建临时文件失败] {e}")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, ENV_FILE)
    except HTTPException:
        raise
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=_diagnose_write_error(ENV_FILE, PROJECT_ROOT) + f"\n[写入错误] {type(e).__name__}: {e}")

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
