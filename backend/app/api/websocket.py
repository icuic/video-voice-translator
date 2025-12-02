"""
WebSocket 实时进度推送
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# 存储活跃的 WebSocket 连接
active_connections: dict[str, WebSocket] = {}


@router.websocket("/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket 连接，实时推送翻译进度"""
    await websocket.accept()
    active_connections[task_id] = websocket
    logger.info(f"WebSocket 连接已建立: task_id={task_id}, 当前连接数: {len(active_connections)}")
    
    try:
        while True:
            # 接收客户端消息（可选）
            data = await websocket.receive_text()
            # 可以处理客户端发送的请求
            logger.info(f"收到 WebSocket 消息: {data}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket 连接断开: task_id={task_id}")
        active_connections.pop(task_id, None)
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        active_connections.pop(task_id, None)


async def send_progress(task_id: str, progress_data: dict):
    """发送进度更新"""
    if task_id in active_connections:
        try:
            await active_connections[task_id].send_json(progress_data)
            logger.info(f"WebSocket 消息已发送: task_id={task_id}, type={progress_data.get('type')}")
        except Exception as e:
            logger.error(f"发送进度失败: {e}")
            active_connections.pop(task_id, None)
    else:
        logger.warning(f"WebSocket 连接不存在: task_id={task_id}, 当前连接数: {len(active_connections)}, 连接列表: {list(active_connections.keys())}")


