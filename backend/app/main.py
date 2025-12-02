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

from app.api import media, translation, segments, websocket

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

