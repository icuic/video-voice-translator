"""
媒体文件上传和下载 API
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from typing import Optional
import os
import shutil
import json
import re
import subprocess
from pathlib import Path

router = APIRouter(prefix="/media", tags=["media"])

# 临时上传目录
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAIL_DIR = Path("data/thumbnails")
THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}


def _resolve_uploaded_file_path(file_id: str) -> Optional[Path]:
    for ext in [".mp4", ".avi", ".mov", ".mkv", ".wav", ".mp3", ".m4a"]:
        candidate = UPLOAD_DIR / f"{file_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def _upload_metadata_path(file_id: str) -> Path:
    return UPLOAD_DIR / f"{file_id}.json"


def load_upload_metadata(file_id: str) -> dict:
    metadata_path = _upload_metadata_path(file_id)
    if not metadata_path.exists():
        return {}

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_upload_metadata(file_id: str, metadata: dict) -> None:
    metadata_path = _upload_metadata_path(file_id)
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def _safe_cache_key(key: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", key).strip("._")
    return cleaned or "thumbnail"


def generate_video_thumbnail(video_path: Path, cache_key: str) -> Path:
    if not video_path.exists():
        raise FileNotFoundError(f"视频不存在: {video_path}")

    thumbnail_path = THUMBNAIL_DIR / f"{_safe_cache_key(cache_key)}.jpg"
    if thumbnail_path.exists() and thumbnail_path.stat().st_mtime >= video_path.stat().st_mtime:
        return thumbnail_path

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        "00:00:01",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        "scale=320:-1",
        str(thumbnail_path),
    ]

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        fallback_command = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=320:-1",
            str(thumbnail_path),
        ]
        subprocess.run(
            fallback_command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    return thumbnail_path


@router.post("/upload")
async def upload_media(file: UploadFile = File(...)):
    """
    上传视频/音频文件
    
    Returns:
        {
            "file_id": "唯一文件ID",
            "filename": "原始文件名",
            "size": 文件大小（字节）,
            "type": "video" | "audio"
        }
    """
    try:
        # 生成唯一文件ID
        import time
        import hashlib
        file_id = hashlib.md5(f"{file.filename}{time.time()}".encode()).hexdigest()
        
        # 确定文件类型
        ext = Path(file.filename).suffix.lower()
        if ext in VIDEO_EXTS:
            file_type = "video"
        elif ext in AUDIO_EXTS:
            file_type = "audio"
        else:
            raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")
        
        # 保存文件
        file_path = UPLOAD_DIR / f"{file_id}{ext}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = file_path.stat().st_size
        _write_upload_metadata(
            file_id,
            {
                "file_id": file_id,
                "original_filename": file.filename,
                "type": file_type,
                "ext": ext,
                "stored_path": str(file_path),
                "size": file_size,
            },
        )
        
        return {
            "file_id": file_id,
            "filename": file.filename,
            "size": file_size,
            "type": file_type,
            "path": str(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.get("/{file_id}")
async def get_media(file_id: str):
    """获取媒体文件（支持流式传输）"""
    file_path = _resolve_uploaded_file_path(file_id)
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=file_path.name
    )


@router.get("/{file_id}/thumbnail")
async def get_media_thumbnail(file_id: str):
    """获取上传视频的缩略图"""
    file_path = _resolve_uploaded_file_path(file_id)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if file_path.suffix.lower() not in VIDEO_EXTS:
        raise HTTPException(status_code=400, detail="当前媒体不是视频，无法生成缩略图")

    try:
        thumbnail_path = generate_video_thumbnail(file_path, file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail="生成缩略图失败") from exc

    return FileResponse(path=thumbnail_path, media_type="image/jpeg")


@router.get("/{file_id}/metadata")
async def get_media_metadata(file_id: str):
    """获取媒体元数据（时长、分辨率等）"""
    # TODO: 实现媒体元数据提取
    # 可以使用现有的 src/metadata_extractor.py
    return {
        "file_id": file_id,
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0
    }


@router.get("/result/{task_id}")
async def get_result_media(task_id: str):
    """获取翻译结果视频/音频文件"""
    # 导入 tasks（从 translation 模块）
    from app.api import translation
    tasks = translation.tasks
    
    # 首先尝试从任务字典中获取
    final_video_path = None
    task_dir = None
    
    if task_id in tasks:
        task = tasks[task_id]
        if task.get("status") != "completed":
            raise HTTPException(status_code=400, detail="翻译任务尚未完成")
        final_video_path = task.get("final_video_path")
        task_dir = task.get("task_dir")
    else:
        # 任务不在字典中（可能因为后端重启），尝试从文件系统查找
        import glob
        outputs_dir = Path("data/outputs")
        if outputs_dir.exists():
            # 查找包含 09_translated 文件的目录（按时间倒序）
            for dir_path in sorted(outputs_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if dir_path.is_dir():
                    video_files = list(dir_path.glob("09_translated_*.mp4"))
                    if video_files:
                        final_video_path = str(video_files[0])
                        task_dir = str(dir_path)
                        break
    
    if not final_video_path:
        raise HTTPException(status_code=404, detail="翻译结果文件不存在")
    
    final_video_path = Path(final_video_path)
    if not final_video_path.exists():
        raise HTTPException(status_code=404, detail=f"翻译结果文件不存在: {final_video_path}")
    
    # 确定媒体类型
    ext = final_video_path.suffix.lower()
    if ext in ['.mp4', '.avi', '.mov', '.mkv']:
        media_type = "video/mp4"
    elif ext in ['.wav', '.mp3', '.m4a']:
        media_type = "audio/mpeg"
    else:
        media_type = "application/octet-stream"
    
    return FileResponse(
        path=final_video_path,
        media_type=media_type,
        filename=final_video_path.name
    )

