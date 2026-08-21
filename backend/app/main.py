"""
FastAPI 应用主入口
提供 REST API 接口，调用 ./src/ 中的业务逻辑
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
import os
import sys
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 添加项目根目录和 backend 目录到 Python 路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, backend_dir)


# Python 层强兜底：从 PROJECT_ROOT/.env 把 LLM_* 写进 os.environ。
# 真实 VM-0-14-ubuntu 环境已证实：即使 shell 启动时 export 了 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL，
# /proc/<uvicorn pid>/environ 里也只有 PROJECT_ROOT（supervisor 启动链路未将额外变量挂到进程环境表上），
# 导致 src/text_translator.py 用 os.getenv('LLM_*') 时全部取不到，直接抛『未配置 LLM 翻译密钥』。
# 这里在 import 业务路由前先写一遍 os.environ，能 100% 覆盖到 FastAPI 主进程、uvicorn worker 进程以及
# 它们 import 的 src/* 模块，彻底消除"磁盘 .env 有值但进程环境没值"的断层。
def _force_llm_env_from_project_dotenv(project_root: str) -> None:
    from pathlib import Path

    env_file = Path(project_root) / ".env"
    if not env_file.is_file():
        return
    want_keys = (
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
        "LLM_TIMEOUT",
        "DASHSCOPE_API_KEY",
        "MIRROR_MODE",
        "HF_ENDPOINT",
        "USE_MODELSCOPE",
    )
    parsed: dict[str, str] = {}
    try:
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'", '`'):
                v = v[1:-1].strip()
            if k in want_keys:
                parsed[k] = v
    except Exception as e:  # pragma: no cover
        logging.getLogger(__name__).warning("读取 PROJECT_ROOT/.env 失败，跳过 LLM env 注入: %s", e)
        return
    applied_count = 0
    for k in want_keys:
        if k not in parsed:
            continue
        if not (os.getenv(k) or "").strip():
            # 这里只能改 os.environ（进程自己的内存表），不能改父 shell；
            # 但对 Python 子进程和 import 的 src/* 模块来说已经足够。
            os.environ[k] = parsed[k]
            applied_count += 1
    logging.getLogger(__name__).info(
        "[main.py] dotenv 注入: applied=%s keys_total=%s want=%s injected=%s",
        applied_count,
        len(parsed),
        ",".join(want_keys),
        ",".join(f"{k}=***" if "KEY" in k or "SECRET" in k else f"{k}={parsed.get(k,'')}" for k in want_keys if k in parsed),
    )


_force_llm_env_from_project_dotenv(project_root)

from app.api import media, translation, segments, websocket, setup

# 中间件：增加请求体大小限制以支持大文件上传
class LargeFileUploadMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 对于上传请求，增加请求体大小限制
        if request.method == "POST" and "/api/media/upload" in str(request.url):
            # Starlette 默认限制是 1MB，这里通过修改 request 的 _receive 来支持大文件
            # 注意：实际限制由 uvicorn 的配置控制
            pass
        response = await call_next(request)
        return response

app = FastAPI(
    title="Video Voice Translator API",
    description="音视频翻译系统 REST API",
    version="1.0.0"
)

# 添加大文件上传中间件
app.add_middleware(LargeFileUploadMiddleware)

# 配置 CORS（允许前端访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（开发环境，生产环境应该限制）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(media.router, prefix="/api", tags=["media"])
app.include_router(translation.router, prefix="/api", tags=["translation"])
app.include_router(segments.router, prefix="/api", tags=["segments"])
app.include_router(websocket.router, prefix="/ws", tags=["websocket"])
app.include_router(setup.router, prefix="/api", tags=["setup"])


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Video Voice Translator API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

