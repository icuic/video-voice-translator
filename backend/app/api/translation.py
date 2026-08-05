"""
翻译任务管理 API
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import sys
import uuid
import asyncio
import logging
import traceback
import threading
import json
import shutil
from pathlib import Path

# 配置日志
logger = logging.getLogger(__name__)

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

router = APIRouter(prefix="/translation", tags=["translation"])

# 任务状态存储（实际应该使用 Redis 或数据库）
tasks: Dict[str, Dict[str, Any]] = {}


class TranslationRequest(BaseModel):
    file_id: str
    source_language: str = "auto"
    target_language: str
    single_speaker: bool = False
    enable_segment_editing: bool = False  # 默认不暂停，直接完成整个流程
    enable_translation_editing: bool = False  # 默认不暂停，直接完成整个流程


class TranslationResponse(BaseModel):
    task_id: str
    status: str  # "pending", "processing", "paused_step4", "paused_step5", "completed", "failed"
    message: str


TASK_STATES_DIR = Path("data/task_states")
OUTPUTS_DIR = Path("data/outputs")


def _load_persisted_task_state(task_id: str) -> Optional[Dict[str, Any]]:
    state_file = TASK_STATES_DIR / f"{task_id}.json"
    if not state_file.exists():
        return None

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取任务状态文件失败: task_id={task_id}, error={e}")
        return None


def _persist_task_state(task: Dict[str, Any]) -> None:
    task_id = task.get("task_id")
    if not task_id:
        return

    TASK_STATES_DIR.mkdir(parents=True, exist_ok=True)
    state_file = TASK_STATES_DIR / f"{task_id}.json"
    tmp_file = TASK_STATES_DIR / f"{task_id}.json.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
    tmp_file.replace(state_file)


def _resolve_final_video_path(task: Dict[str, Any]) -> Optional[str]:
    final_video_path = task.get("final_video_path")
    if final_video_path and Path(final_video_path).exists():
        return final_video_path

    task_dir = task.get("task_dir")
    if task_dir:
        task_dir_path = Path(task_dir)
        if task_dir_path.exists():
            video_files = sorted(task_dir_path.glob("09_translated_*.mp4"))
            if video_files:
                return str(video_files[0])

    return None


def _load_task_params(task_dir: Optional[str]) -> Dict[str, Any]:
    if not task_dir:
        return {}

    task_params_path = Path(task_dir) / "00_task_params.json"
    if not task_params_path.exists():
        return {}

    try:
        with open(task_params_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取任务参数失败: task_dir={task_dir}, error={e}")
        return {}


def _resolve_original_input_path(task: Dict[str, Any]) -> Optional[str]:
    task_dir = task.get("task_dir")
    if task_dir:
        task_dir_path = Path(task_dir)
        if task_dir_path.exists():
            original_candidates = sorted(task_dir_path.glob("00_original_input.*"))
            if original_candidates:
                return str(original_candidates[0])

    file_path = task.get("file_path")
    if file_path and Path(file_path).exists():
        return file_path

    return None


def _resolve_media_type(task: Dict[str, Any]) -> str:
    file_id = task.get("file_id")
    if file_id:
        try:
            from app.api import media as media_api

            upload_metadata = media_api.load_upload_metadata(file_id)
            if upload_metadata.get("type") in {"video", "audio"}:
                return upload_metadata["type"]
        except Exception:
            pass

    candidate_path = _resolve_original_input_path(task) or _resolve_final_video_path(task) or task.get("file_path")
    if candidate_path:
        ext = Path(candidate_path).suffix.lower()
        if ext in {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}:
            return "video"
        if ext in {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}:
            return "audio"

    return "unknown"


def _resolve_original_filename(task: Dict[str, Any]) -> str:
    original_filename = task.get("original_filename")
    if original_filename:
        return original_filename

    file_id = task.get("file_id")
    if file_id:
        try:
            from app.api import media as media_api

            upload_metadata = media_api.load_upload_metadata(file_id)
            metadata_name = upload_metadata.get("original_filename")
            if metadata_name:
                return metadata_name
        except Exception:
            pass

    task_params = _load_task_params(task.get("task_dir"))
    task_params_input_path = task_params.get("input_path")
    if task_params_input_path:
        return Path(task_params_input_path).name

    file_path = task.get("file_path")
    if file_path:
        return Path(file_path).name

    return ""


def _resolve_thumbnail_url(task: Dict[str, Any]) -> Optional[str]:
    if _resolve_media_type(task) != "video":
        return None

    file_id = task.get("file_id")
    if file_id:
        return f"/api/media/{file_id}/thumbnail"

    task_id = task.get("task_id")
    if task_id:
        return f"/api/translation/{task_id}/thumbnail"

    return None


def _build_history_item(task: Dict[str, Any]) -> Dict[str, Any]:
    file_path = task.get("file_path")
    stored_file_name = Path(file_path).name if file_path else ""
    file_name = _resolve_original_filename(task) or stored_file_name
    task_dir = task.get("task_dir")
    task_dir_name = Path(task_dir).name if task_dir else ""
    final_video_path = _resolve_final_video_path(task)
    media_type = _resolve_media_type(task)

    return {
        "task_id": task.get("task_id", ""),
        "file_id": task.get("file_id", ""),
        "file_path": file_path,
        "file_name": file_name,
        "original_filename": file_name,
        "stored_file_name": stored_file_name,
        "status": task.get("status", "unknown"),
        "message": task.get("message", ""),
        "step_name": task.get("step_name", ""),
        "updated_at": task.get("updated_at"),
        "source_language": task.get("source_language", ""),
        "target_language": task.get("target_language", ""),
        "media_type": media_type,
        "task_dir": task_dir,
        "task_dir_name": task_dir_name,
        "final_video_path": final_video_path,
        "thumbnail_url": _resolve_thumbnail_url(task),
    }


def _list_persisted_tasks(limit: int = 20, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    if not TASK_STATES_DIR.exists():
        return []

    task_files = sorted(
        TASK_STATES_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    items: List[Dict[str, Any]] = []
    for task_file in task_files:
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)
            item = _build_history_item(task)
            if status_filter and item.get("status") != status_filter:
                continue
            items.append(item)
        except Exception as e:
            logger.warning(f"读取历史任务失败: {task_file}, error={e}")

        if len(items) >= limit:
            break

    return items


def _list_in_memory_tasks(limit: int = 20, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for task in tasks.values():
        item = _build_history_item(task)
        if status_filter and item.get("status") != status_filter:
            continue
        items.append(item)
    items.sort(key=lambda x: x.get("updated_at") or 0, reverse=True)
    return items[:limit]


@router.post("/start", response_model=TranslationResponse)
async def start_translation(
    request: TranslationRequest,
    background_tasks: BackgroundTasks
):
    """启动翻译任务"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 查找上传的文件
        import sys
        upload_dir = Path("data/uploads")
        print(f"[DEBUG] 查找文件: upload_dir={upload_dir.absolute()}, file_id={request.file_id}", file=sys.stderr, flush=True)
        file_path = None
        for ext in ['.mp4', '.avi', '.mov', '.mkv', '.wav', '.mp3', '.m4a']:
            candidate = upload_dir / f"{request.file_id}{ext}"
            print(f"[DEBUG] 检查文件: {candidate.absolute()} exists={candidate.exists()}", file=sys.stderr, flush=True)
            if candidate.exists():
                file_path = str(candidate)
                break

        if not file_path:
            print(f"[DEBUG] 文件不存在，列出目录内容:", file=sys.stderr, flush=True)
            if upload_dir.exists():
                for f in upload_dir.iterdir():
                    print(f"[DEBUG] 找到文件: {f}", file=sys.stderr, flush=True)
            raise HTTPException(status_code=404, detail="上传的文件不存在")

        upload_metadata: Dict[str, Any] = {}
        try:
            from app.api import media as media_api

            upload_metadata = media_api.load_upload_metadata(request.file_id)
        except Exception:
            upload_metadata = {}
        
        # 初始化任务状态
        tasks[task_id] = {
            "task_id": task_id,
            "file_id": request.file_id,
            "file_path": file_path,
            "original_filename": upload_metadata.get("original_filename", ""),
            "media_type": upload_metadata.get("type", ""),
            "status": "pending",
            "current_step": 0,
            "progress": 0.0,
            "message": "任务已创建，等待处理...",
            "step_name": "",
            "updated_at": int(__import__("time").time() * 1000),
            "current_segment": 0,
            "total_segments": 0,
            "source_language": request.source_language,
            "target_language": request.target_language,
            "single_speaker": request.single_speaker,
            "enable_segment_editing": request.enable_segment_editing,
            "enable_translation_editing": request.enable_translation_editing,
        }
        _persist_task_state(tasks[task_id])
        # 使用多种方式确保日志输出
        import sys
        import os
        # 验证任务是否真的在字典中
        if task_id in tasks:
            log_msg = f"[LOG] 任务已创建: task_id={task_id}, 任务字典大小={len(tasks)}, status={tasks[task_id]['status']}\n"
        else:
            log_msg = f"[ERROR] 任务创建失败: task_id={task_id}, 任务不在字典中！\n"
        print(log_msg, file=sys.stderr, flush=True)
        # 同时写入日志文件（使用追加模式，确保不会覆盖）
        try:
            with open("/tmp/backend.log", "a", encoding="utf-8") as f:
                f.write(log_msg)
                f.flush()
            # 再次验证任务是否在字典中
            if task_id not in tasks:
                error_msg = f"[ERROR] 任务创建后立即消失: task_id={task_id}\n"
                print(error_msg, file=sys.stderr, flush=True)
                with open("/tmp/backend.log", "a", encoding="utf-8") as f:
                    f.write(error_msg)
                    f.flush()
        except Exception as e:
            error_msg = f"[ERROR] 写入日志文件失败: {e}\n"
            print(error_msg, file=sys.stderr, flush=True)
        logger.info(f"任务已创建: task_id={task_id}, 任务字典大小={len(tasks)}")
        
        # 在后台执行翻译任务（使用线程立即执行，而不是 BackgroundTasks）
        logger.info(f"启动翻译任务: task_id={task_id}, file_path={file_path}, source_lang={request.source_language}, target_lang={request.target_language}")
        import sys
        print(f"[LOG] 启动翻译任务: task_id={task_id}", file=sys.stderr, flush=True)  # 使用 stderr 并立即刷新
        
        # 立即更新状态为 processing，让前端能立即看到进度
        tasks[task_id]["status"] = "processing"
        tasks[task_id]["current_step"] = 1
        tasks[task_id]["progress"] = 1.0  # 初始进度1%
        tasks[task_id]["message"] = "正在启动翻译任务..."
        tasks[task_id]["step_name"] = "初始化中..."
        tasks[task_id]["updated_at"] = int(__import__("time").time() * 1000)
        _persist_task_state(tasks[task_id])
        logger.info(f"任务状态已立即更新为 processing: task_id={task_id}")
        print(f"[LOG] 任务状态已立即更新为 processing: task_id={task_id}, progress=1%", file=sys.stderr, flush=True)  # 使用 stderr 并立即刷新
        
        # 使用线程立即执行任务，确保状态能及时更新
        task_thread = threading.Thread(
            target=execute_translation_task,
            args=(
                task_id,
                file_path,
                request.source_language,
                request.target_language,
                request.single_speaker,
                request.enable_segment_editing,
                request.enable_translation_editing
            ),
            daemon=True
        )
        task_thread.start()
        logger.info(f"后台任务线程已启动: task_id={task_id}")
        import sys
        print(f"[LOG] 后台任务线程已启动: task_id={task_id}", file=sys.stderr, flush=True)  # 使用 stderr 并立即刷新
        
        # 返回最新的任务状态
        return TranslationResponse(
            task_id=task_id,
            status=tasks[task_id]["status"],  # 返回最新状态（应该是 "processing"）
            message=tasks[task_id]["message"]  # 返回最新消息
        )
    except Exception as e:
        import sys
        import traceback
        error_msg = f"启动翻译任务失败: {str(e)}\n{traceback.format_exc()}"
        print(f"[ERROR] {error_msg}", file=sys.stderr, flush=True)
        # 同时写入日志文件
        try:
            with open("/tmp/backend.log", "a", encoding="utf-8") as f:
                f.write(f"[ERROR] {error_msg}\n")
                f.flush()
        except:
            pass
        logger.error(f"启动翻译任务失败: {error_msg}")
        raise HTTPException(status_code=500, detail=f"启动翻译任务失败: {str(e)}")


@router.get("/history")
async def list_translation_history(limit: int = 20, status: Optional[str] = None):
    """列出最近的历史任务"""
    safe_limit = max(1, min(limit, 100))
    status_filter = status or None
    persisted = _list_persisted_tasks(safe_limit, status_filter=status_filter)
    persisted_ids = {item.get("task_id") for item in persisted if item.get("task_id")}
    in_memory = [item for item in _list_in_memory_tasks(safe_limit, status_filter=status_filter) if item.get("task_id") not in persisted_ids]
    items = (in_memory + persisted)[:safe_limit]
    return {"tasks": items}


@router.delete("/history/{task_id}")
async def delete_translation_history(task_id: str):
    """删除某一项历史任务"""
    state_file = TASK_STATES_DIR / f"{task_id}.json"
    persisted_task = _load_persisted_task_state(task_id)
    in_memory_task = tasks.get(task_id)
    task_data = persisted_task or in_memory_task

    if not task_data and not state_file.exists():
        raise HTTPException(status_code=404, detail="历史任务不存在")

    deleted_state_file = False
    deleted_output_dir = False
    deleted_output_dir_path = None

    if task_id in tasks:
        del tasks[task_id]

    if state_file.exists():
        state_file.unlink()
        deleted_state_file = True

    task_dir = task_data.get("task_dir") if task_data else None
    if task_dir:
        task_dir_path = Path(task_dir)
        resolved_task_dir = task_dir_path.resolve()
        resolved_outputs_dir = OUTPUTS_DIR.resolve()
        try:
            resolved_task_dir.relative_to(resolved_outputs_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="任务输出目录不合法，已拒绝删除") from exc

        if resolved_task_dir.exists():
            shutil.rmtree(resolved_task_dir)
            deleted_output_dir = True
            deleted_output_dir_path = str(task_dir_path)

    return {
        "task_id": task_id,
        "deleted_state_file": deleted_state_file,
        "deleted_output_dir": deleted_output_dir,
        "deleted_output_dir_path": deleted_output_dir_path,
    }


@router.get("/{task_id}/thumbnail")
async def get_translation_thumbnail(task_id: str):
    """获取历史任务的缩略图"""
    task = tasks.get(task_id) or _load_persisted_task_state(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    thumbnail_source = _resolve_original_input_path(task) or _resolve_final_video_path(task)
    if not thumbnail_source:
        raise HTTPException(status_code=404, detail="当前任务没有可用的视频缩略图")

    thumbnail_source_path = Path(thumbnail_source)
    if thumbnail_source_path.suffix.lower() not in {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}:
        raise HTTPException(status_code=400, detail="当前任务不是视频任务，无法生成缩略图")

    try:
        from app.api import media as media_api

        thumbnail_path = media_api.generate_video_thumbnail(thumbnail_source_path, f"task-{task_id}")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="生成缩略图失败") from exc

    return FileResponse(path=thumbnail_path, media_type="image/jpeg")


def execute_translation_task(
    task_id: str,
    file_path: str,
    source_lang: str,
    target_lang: str,
    single_speaker: bool,
    enable_segment_editing: bool,
    enable_translation_editing: bool
):
    """执行翻译任务（后台任务）"""
    # 注意：BackgroundTasks 不支持 async 函数，所以这里改为同步函数
    # 但 translate_media 是同步的，所以没问题
    logger.info(f"开始执行翻译任务: task_id={task_id}, file_path={file_path}")
    import sys
    print(f"[LOG] 开始执行翻译任务: task_id={task_id}", file=sys.stderr, flush=True)  # 使用 stderr 并立即刷新
    
    try:
        # 立即更新任务状态
        import sys
        print(f"[LOG] execute_translation_task 开始执行: task_id={task_id}, 任务字典大小={len(tasks)}", file=sys.stderr, flush=True)
        logger.info(f"execute_translation_task 开始执行: task_id={task_id}, 任务字典大小={len(tasks)}")
        
        if task_id not in tasks:
            logger.error(f"任务不存在: task_id={task_id}, 任务字典大小={len(tasks)}")
            print(f"[ERROR] 任务不存在，无法执行: task_id={task_id}, 任务字典大小={len(tasks)}", file=sys.stderr, flush=True)
            # 列出所有任务ID
            if tasks:
                print(f"[ERROR] 当前任务字典中的任务: {list(tasks.keys())}", file=sys.stderr, flush=True)
            return
        
        tasks[task_id]["status"] = "processing"
        tasks[task_id]["current_step"] = 1
        tasks[task_id]["progress"] = 5.0  # 初始进度5%
        tasks[task_id]["message"] = "开始翻译..."
        tasks[task_id]["step_name"] = "准备中..."
        tasks[task_id]["current_segment"] = 0
        tasks[task_id]["total_segments"] = 0
        logger.info(f"任务状态已更新为 processing: task_id={task_id}, progress=5.0%")
        import sys
        print(f"[LOG] 任务状态已更新为 processing: task_id={task_id}, progress=5.0%", file=sys.stderr, flush=True)  # 使用 stderr 并立即刷新
        
        # 定义步骤名称
        step_names = [
            "步骤1: 音频提取",
            "步骤2: 音频分离",
            "步骤3: 多说话人处理",
            "步骤4: 语音识别",
            "步骤5: 文本翻译",
            "步骤6: 参考音频提取",
            "步骤7: 音色克隆",
            "步骤8: 音频合并",
            "步骤9: 视频合成"
        ]
        
        # 定义进度回调函数
        def update_progress(step_index: int, step_name: str, progress_pct: float, 
                          message: str = "", current_segment: int = 0, total_segments: int = 0):
            """更新任务进度"""
            if task_id in tasks:
                tasks[task_id]["current_step"] = step_index
                tasks[task_id]["step_name"] = step_name
                tasks[task_id]["progress"] = progress_pct
                tasks[task_id]["current_segment"] = current_segment
                tasks[task_id]["total_segments"] = total_segments
                tasks[task_id]["updated_at"] = int(__import__("time").time() * 1000)
                if message:
                    tasks[task_id]["message"] = message
                elif current_segment > 0 and total_segments > 0:
                    tasks[task_id]["message"] = f"{step_name} ({current_segment}/{total_segments})"
                else:
                    tasks[task_id]["message"] = step_name
                _persist_task_state(tasks[task_id])
                # 添加日志输出，确保能看到进度更新
                import sys
                print(f"[LOG] 进度更新: task_id={task_id}, step={step_index}, progress={progress_pct:.1f}%, message={tasks[task_id]['message']}", file=sys.stderr, flush=True)
                logger.info(f"进度更新: task_id={task_id}, step={step_index}, progress={progress_pct:.1f}%, message={tasks[task_id]['message']}")
            else:
                import sys
                print(f"[ERROR] 任务不存在，无法更新进度: task_id={task_id}", file=sys.stderr, flush=True)
                logger.error(f"任务不存在，无法更新进度: task_id={task_id}")
        
        # 在翻译开始前更新进度
        update_progress(1, "步骤1: 音频提取", 5.0, "正在启动翻译任务...")  # 初始进度5%
        
        # 调用翻译函数，现在支持实时进度回调
        from media_translation_cli import translate_media
        
        logger.info(f"开始调用 translate_media: task_id={task_id}")
        print(f"[LOG] 开始调用 translate_media: task_id={task_id}", file=sys.stderr, flush=True)

        # 添加调试信息
        print(f"[DEBUG] 调用translate_media前: task_id={task_id}, file_path={file_path}", file=sys.stderr, flush=True)

        result = translate_media(
            input_path=file_path,
            source_lang=source_lang,
            target_lang=target_lang,
            output_dir="data/outputs",
            voice_model="index-tts2",
            single_speaker=single_speaker,
            pause_after_step4=enable_segment_editing,
            pause_after_step5=enable_translation_editing,
            webui_mode=True,
            progress_callback=update_progress
        )

        print(f"[DEBUG] translate_media 返回: success={result.get('success', False)}, error={result.get('error', 'None')}", file=sys.stderr, flush=True)
        logger.info(f"translate_media 执行完成: task_id={task_id}, success={result.get('success', False)}")
        
        # 如果成功，从结果中获取 task_dir
        if result.get("success") and result.get("task_dir"):
            tasks[task_id]["task_dir"] = result.get("task_dir")
            logger.info(f"任务目录已设置: task_id={task_id}, task_dir={result.get('task_dir')}")
        
        # 更新任务状态
        if result.get("success"):
            logger.info(f"翻译任务成功完成: task_id={task_id}")
            if result.get("needs_segment_editing"):
                tasks[task_id]["status"] = "paused_step4"
                tasks[task_id]["message"] = "步骤4完成，请编辑分段"
                tasks[task_id]["task_dir"] = result.get("task_dir")
                tasks[task_id]["segments_file"] = result.get("segments_file")
                logger.info(f"任务暂停在步骤4: task_id={task_id}")
            elif result.get("needs_editing"):
                tasks[task_id]["status"] = "paused_step5"
                tasks[task_id]["message"] = "步骤5完成，请编辑翻译结果"
                tasks[task_id]["task_dir"] = result.get("task_dir")
                tasks[task_id]["translation_file"] = result.get("translation_file")
                logger.info(f"任务暂停在步骤5: task_id={task_id}")
            else:
                # 任务完全完成，更新所有状态
                logger.info(f"任务完全完成，更新状态: task_id={task_id}")
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["message"] = "翻译完成"
                tasks[task_id]["current_step"] = 9  # 步骤9完成
                tasks[task_id]["progress"] = 100.0  # 进度100%
                tasks[task_id]["step_name"] = "步骤9: 视频合成"
                tasks[task_id]["current_segment"] = 0
                tasks[task_id]["total_segments"] = 0
                tasks[task_id]["final_video_path"] = result.get("final_video_path")
                tasks[task_id]["final_audio_path"] = result.get("final_audio_path")
                tasks[task_id]["task_dir"] = result.get("task_dir")
                tasks[task_id]["updated_at"] = int(__import__("time").time() * 1000)
                _persist_task_state(tasks[task_id])
                logger.info(f"任务完成，状态已更新: task_id={task_id}, progress={tasks[task_id]['progress']}, step={tasks[task_id]['current_step']}, final_video_path={result.get('final_video_path')}")
        else:
            error_msg = result.get("error", "翻译失败")
            logger.error(f"翻译任务失败: task_id={task_id}, error={error_msg}")
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["message"] = error_msg
            tasks[task_id]["updated_at"] = int(__import__("time").time() * 1000)
            _persist_task_state(tasks[task_id])
            
    except Exception as e:
        error_msg = f"翻译任务执行失败: {str(e)}"
        error_trace = traceback.format_exc()
        logger.error(f"任务执行失败: task_id={task_id}, error={error_msg}")
        logger.error(f"异常堆栈: {error_trace}")
        
        if task_id in tasks:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["message"] = error_msg
            tasks[task_id]["updated_at"] = int(__import__("time").time() * 1000)
            _persist_task_state(tasks[task_id])
        else:
            logger.error(f"任务不存在，无法更新状态: task_id={task_id}")


@router.get("/{task_id}/status")
async def get_translation_status(task_id: str):
    """获取翻译任务状态"""
    if task_id not in tasks:
        persisted_task = _load_persisted_task_state(task_id)
        if not persisted_task:
            raise HTTPException(status_code=404, detail="任务不存在")

        return {
            "task_id": task_id,
            "status": persisted_task.get("status", "unknown"),
            "file_id": persisted_task.get("file_id", ""),
            "current_step": persisted_task.get("current_step", 0),
            "progress": persisted_task.get("progress", 0.0),
            "message": persisted_task.get("message", ""),
            "step_name": persisted_task.get("step_name", ""),
            "current_segment": persisted_task.get("current_segment", 0),
            "total_segments": persisted_task.get("total_segments", 0),
            "task_dir": persisted_task.get("task_dir"),
            "final_video_path": _resolve_final_video_path(persisted_task),
            "final_audio_path": persisted_task.get("final_audio_path"),
            "source_language": persisted_task.get("source_language", ""),
            "target_language": persisted_task.get("target_language", ""),
        }
    
    task = tasks[task_id]
    return {
        "task_id": task_id,
        "file_id": task.get("file_id", ""),
        "status": task["status"],
        "current_step": task.get("current_step", 0),
        "progress": task.get("progress", 0.0),
        "message": task.get("message", ""),
        "step_name": task.get("step_name", ""),
        "current_segment": task.get("current_segment", 0),
        "total_segments": task.get("total_segments", 0),
        "task_dir": task.get("task_dir"),
        "final_video_path": _resolve_final_video_path(task),
        "final_audio_path": task.get("final_audio_path"),
        "source_language": task.get("source_language", ""),
        "target_language": task.get("target_language", ""),
    }


@router.get("/{task_id}/progress")
async def get_translation_progress(task_id: str):
    """获取翻译进度（当前步骤、百分比）"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = tasks[task_id]
    return {
        "task_id": task_id,
        "step": task.get("current_step", 0),
        "progress": task.get("progress", 0.0),
        "message": task.get("message", ""),
    }


@router.post("/{task_id}/continue")
async def continue_translation(task_id: str):
    """继续翻译（在步骤4或5暂停后）"""
    # TODO: 实现继续翻译逻辑
    return {"message": "继续翻译功能待实现"}


@router.get("/{task_id}/result")
async def get_translation_result(task_id: str):
    """获取翻译结果（视频/音频文件）"""
    if task_id not in tasks:
        persisted_task = _load_persisted_task_state(task_id)
        if not persisted_task:
            raise HTTPException(status_code=404, detail="任务不存在")

        if persisted_task.get("status") != "completed":
            raise HTTPException(status_code=400, detail="翻译任务尚未完成")

        return {
            "task_id": task_id,
            "video_path": _resolve_final_video_path(persisted_task),
            "audio_path": persisted_task.get("final_audio_path"),
            "task_dir": persisted_task.get("task_dir"),
        }
    
    task = tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="翻译任务尚未完成")
    
    return {
        "task_id": task_id,
        "video_path": _resolve_final_video_path(task),
        "audio_path": task.get("final_audio_path"),
        "task_dir": task.get("task_dir"),
    }
