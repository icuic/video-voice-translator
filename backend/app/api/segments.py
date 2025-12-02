"""
分段管理 API
包含单个分段的重新翻译和重新合成功能
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import sys
import json
import logging
import traceback
from pathlib import Path

logger = logging.getLogger(__name__)

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from app.services import segment_service

router = APIRouter(prefix="/segments", tags=["segments"])


class Segment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    speaker_id: Optional[str] = None
    words: Optional[List[dict]] = None
    translated_text: Optional[str] = None


class UpdateSegmentsRequest(BaseModel):
    segments: List[Segment]


class RetranslateRequest(BaseModel):
    new_text: Optional[str] = None  # 如果提供，直接使用；否则自动翻译


class ResynthesizeRequest(BaseModel):
    use_original_timbre: bool = True


@router.get("/{task_id}")
async def get_segments(task_id: str):
    """获取分段列表"""
    try:
        segments = await segment_service.get_segments(task_id)
        return {"segments": segments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分段失败: {str(e)}")


@router.put("/{task_id}")
async def update_segments(task_id: str, request: UpdateSegmentsRequest):
    """更新分段（编辑、合并、拆分、删除）"""
    try:
        result = await segment_service.update_segments(task_id, [s.dict() for s in request.segments])
        return {"success": True, "segments": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新分段失败: {str(e)}")


@router.post("/{task_id}/segments/{segment_id}/retranslate")
async def retranslate_segment(
    task_id: str,
    segment_id: int,
    request: RetranslateRequest
):
    """
    重新翻译单个分段
    
    Args:
        task_id: 任务ID
        segment_id: 分段ID
        request: 包含可选的新翻译文本
    """
    try:
        result = await segment_service.retranslate_segment(
            task_id, segment_id, request.new_text
        )
        return {"success": True, "segment": result}
    except Exception as e:
        import traceback
        error_detail = f"重新翻译失败: {str(e)}"
        error_trace = traceback.format_exc()
        logger.error(f"{error_detail}\n{error_trace}")
        raise HTTPException(status_code=500, detail=error_detail)


@router.post("/{task_id}/segments/{segment_id}/resynthesize")
async def resynthesize_segment(
    task_id: str,
    segment_id: int,
    request: ResynthesizeRequest,
    background_tasks: BackgroundTasks
):
    """
    重新合成单个分段的语音
    
    Args:
        task_id: 任务ID
        segment_id: 分段ID
        request: 包含是否使用原音色的选项
    """
    try:
        # 在后台执行重新合成（因为可能需要较长时间）
        background_tasks.add_task(
            segment_service.resynthesize_segment,
            task_id,
            segment_id,
            request.use_original_timbre
        )
        return {
            "success": True,
            "message": "重新合成任务已启动，请通过 WebSocket 查看进度"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动重新合成失败: {str(e)}")


@router.post("/{task_id}/merge")
async def merge_segments(task_id: str, segment_ids: List[int]):
    """合并分段"""
    try:
        result = await segment_service.merge_segments(task_id, segment_ids)
        return {"success": True, "segments": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合并分段失败: {str(e)}")


class SplitSegmentRequest(BaseModel):
    split_time: Optional[float] = None
    split_text: Optional[str] = None
    split_text_position: Optional[int] = None


@router.post("/{task_id}/split")
async def split_segment(
    task_id: str,
    segment_id: int = Query(..., description="分段ID"),
    request: SplitSegmentRequest = SplitSegmentRequest()
):
    """拆分分段"""
    try:
        # 参数优先级：split_time > split_text_position > split_text
        result = await segment_service.split_segment(
            task_id, segment_id, 
            request.split_time, 
            request.split_text, 
            request.split_text_position
        )
        return {"success": True, "segments": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拆分分段失败: {str(e)}")


@router.delete("/{task_id}")
async def delete_segments(task_id: str, segment_ids: List[int]):
    """删除分段"""
    try:
        result = await segment_service.delete_segments(task_id, segment_ids)
        return {"success": True, "segments": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除分段失败: {str(e)}")


@router.post("/{task_id}/regenerate-final")
async def regenerate_final(task_id: str, background_tasks: BackgroundTasks):
    """
    重新生成最终音频和视频（在所有分段编辑完成后）
    """
    try:
        background_tasks.add_task(
            segment_service.regenerate_final_media,
            task_id
        )
        return {
            "success": True,
            "message": "重新生成任务已启动，请通过 WebSocket 查看进度"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动重新生成失败: {str(e)}")


@router.get("/{task_id}/segments/{segment_id}/ref-audio")
async def get_ref_audio(task_id: str, segment_id: int):
    """
    获取原始音频文件（ref_audio）

    对于拆分后的分段，如果对应的音频文件不存在，
    会尝试使用第一个可用的参考音频文件。
    
    Args:
        task_id: 任务ID
        segment_id: 分段ID
    """
    try:
        # 查找任务目录
        task_dir = segment_service.find_task_dir(task_id)
        if not task_dir:
            raise HTTPException(status_code=404, detail=f"任务目录不存在: {task_id}")
        
        ref_audio_dir = os.path.join(task_dir, "ref_audio")
        if not os.path.exists(ref_audio_dir):
            raise HTTPException(status_code=404, detail=f"参考音频目录不存在: {ref_audio_dir}")

        # 首先尝试使用对应的 segment_id
        audio_file = os.path.join(ref_audio_dir, f"06_ref_segment_{segment_id:03d}.wav")
        if os.path.exists(audio_file):
            return FileResponse(
                path=audio_file,
                media_type="audio/wav",
                filename=f"ref_segment_{segment_id:03d}.wav"
            )

        # 如果对应的文件不存在（通常是拆分后的分段），使用第一个可用的参考音频
        ref_files = sorted([f for f in os.listdir(ref_audio_dir) if f.endswith('.wav')])
        if ref_files:
            fallback_audio = os.path.join(ref_audio_dir, ref_files[0])
            logger.info(f"为分段 {segment_id} 使用默认参考音频: {fallback_audio}")
            return FileResponse(
                path=fallback_audio,
                media_type="audio/wav",
                filename=f"ref_segment_{segment_id:03d}.wav"
            )

        raise HTTPException(status_code=404, detail=f"未找到任何参考音频文件")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取原始音频失败: {str(e)}")


@router.get("/{task_id}/segments/{segment_id}/cloned-audio")
async def get_cloned_audio(task_id: str, segment_id: int):
    """
    获取克隆音频文件（cloned_audio）

    Args:
        task_id: 任务ID
        segment_id: 分段ID
    """
    try:
        # 查找任务目录
        task_dir = segment_service.find_task_dir(task_id)
        if not task_dir:
            raise HTTPException(status_code=404, detail=f"任务目录不存在: {task_id}")

        # 构建克隆音频文件路径
        audio_file = os.path.join(task_dir, "cloned_audio", f"07_segment_{segment_id:03d}.wav")

        # 检查文件是否存在
        if not os.path.exists(audio_file):
            raise HTTPException(status_code=404, detail=f"克隆音频文件不存在: {audio_file}")

        return FileResponse(
            path=audio_file,
            media_type="audio/wav",
            filename=f"cloned_segment_{segment_id:03d}.wav"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取克隆音频失败: {str(e)}")


@router.get("/{task_id}/segments/{segment_id}/status")
async def get_segment_status(task_id: str, segment_id: int):
    """
    获取分段的合成状态

    Args:
        task_id: 任务ID
        segment_id: 分段ID

    Returns:
        dict: 包含合成状态和音频路径的信息
    """
    try:
        # 查找任务目录
        task_dir = segment_service.find_task_dir(task_id)
        if not task_dir:
            raise HTTPException(status_code=404, detail=f"任务目录不存在: {task_id}")

        # 构建克隆音频文件路径
        audio_file = os.path.join(task_dir, "cloned_audio", f"07_segment_{segment_id:03d}.wav")

        # 检查文件是否存在
        if os.path.exists(audio_file):
            return {
                "segment_id": segment_id,
                "status": "completed",
                "audio_path": f"/api/segments/{task_id}/segments/{segment_id}/cloned-audio",
                "file_exists": True
            }
        else:
            return {
                "segment_id": segment_id,
                "status": "pending",
                "audio_path": None,
                "file_exists": False
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分段状态失败: {str(e)}")

