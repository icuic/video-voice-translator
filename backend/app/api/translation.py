"""
翻译任务管理 API
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import sys
import uuid
import asyncio
import logging
import traceback
import threading
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
        
        # 初始化任务状态
        tasks[task_id] = {
            "task_id": task_id,
            "file_id": request.file_id,
            "file_path": file_path,
            "status": "pending",
            "current_step": 0,
            "progress": 0.0,
            "message": "任务已创建，等待处理...",
            "step_name": "",
            "current_segment": 0,
            "total_segments": 0,
            "source_language": request.source_language,
            "target_language": request.target_language,
            "single_speaker": request.single_speaker,
            "enable_segment_editing": request.enable_segment_editing,
            "enable_translation_editing": request.enable_translation_editing,
        }
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
                if message:
                    tasks[task_id]["message"] = message
                elif current_segment > 0 and total_segments > 0:
                    tasks[task_id]["message"] = f"{step_name} ({current_segment}/{total_segments})"
                else:
                    tasks[task_id]["message"] = step_name
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
                logger.info(f"任务完成，状态已更新: task_id={task_id}, progress={tasks[task_id]['progress']}, step={tasks[task_id]['current_step']}, final_video_path={result.get('final_video_path')}")
        else:
            error_msg = result.get("error", "翻译失败")
            logger.error(f"翻译任务失败: task_id={task_id}, error={error_msg}")
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["message"] = error_msg
            
    except Exception as e:
        error_msg = f"翻译任务执行失败: {str(e)}"
        error_trace = traceback.format_exc()
        logger.error(f"任务执行失败: task_id={task_id}, error={error_msg}")
        logger.error(f"异常堆栈: {error_trace}")
        
        if task_id in tasks:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["message"] = error_msg
        else:
            logger.error(f"任务不存在，无法更新状态: task_id={task_id}")


@router.get("/{task_id}/status")
async def get_translation_status(task_id: str):
    """获取翻译任务状态"""
    if task_id not in tasks:
        # 任务不在字典中，可能是任务已完成或被清空
        # 这里暂时不做文件系统检查，直接返回不存在
        # TODO: 可以考虑添加任务持久化存储
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = tasks[task_id]
    return {
        "task_id": task_id,
        "status": task["status"],
        "current_step": task.get("current_step", 0),
        "progress": task.get("progress", 0.0),
        "message": task.get("message", ""),
        "step_name": task.get("step_name", ""),
        "current_segment": task.get("current_segment", 0),
        "total_segments": task.get("total_segments", 0),
        "task_dir": task.get("task_dir"),
        "final_video_path": task.get("final_video_path"),
        "final_audio_path": task.get("final_audio_path"),
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
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="翻译任务尚未完成")
    
    return {
        "task_id": task_id,
        "video_path": task.get("final_video_path"),
        "audio_path": task.get("final_audio_path"),
        "task_dir": task.get("task_dir"),
    }


