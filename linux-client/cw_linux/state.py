# coding: utf-8
"""
客户端状态管理模块（自 core/client/state.py 精简移植）
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from .app import CapsWriterClient
    try:
        from websockets.legacy.client import WebSocketClientProtocol
    except Exception:
        WebSocketClientProtocol = Any

from rich.console import Console
from rich.theme import Theme

from .logger import get_logger

logger = get_logger('client')

# 配置 Rich console
_theme = Theme({
    'markdown.code': 'cyan',
    'markdown.item.number': 'yellow'
})
console = Console(highlight=False, soft_wrap=True, theme=_theme)


@dataclass
class ClientState:
    """
    客户端运行状态

    Attributes:
        loop: asyncio 事件循环
        queue_in: 音频数据输入队列
        websocket: WebSocket 客户端连接
        stream: 音频输入流
        recording: 是否正在录音
        recording_start_time: 录音开始时间戳
        audio_files: 任务ID到音频文件路径的映射
    """

    queue_in: asyncio.Queue = field(default_factory=asyncio.Queue)
    queue_out: asyncio.Queue = field(default_factory=asyncio.Queue)
    websocket: Optional[Any] = None
    stream: Optional[Any] = None
    app: Optional['CapsWriterClient'] = None

    recording: bool = False
    recording_start_time: float = 0.0
    audio_files: Dict[str, Path] = field(default_factory=dict)

    # 最近一次输出内容（供复制菜单等使用）
    last_output_text: Optional[str] = None

    def reset(self) -> None:
        """重置状态，关闭连接与音频流"""
        logger.debug("正在重置客户端状态...")

        ws = self.websocket
        if ws is not None:
            try:
                if self.app and self.app.loop and self.app.loop.is_running():
                    asyncio.run_coroutine_threadsafe(ws.close(), self.app.loop)
            except Exception:
                pass
            self.websocket = None

        if self.stream is not None:
            try:
                self.stream.close()
                logger.debug("音频流已关闭")
            except Exception:
                pass
            self.stream = None

        self.recording = False
        self.recording_start_time = 0.0
        self.audio_files.clear()
        logger.debug("客户端状态重置完成")

    def start_recording(self, start_time: float) -> None:
        """标记开始录音"""
        self.recording = True
        self.recording_start_time = start_time
        logger.debug("录音状态已更新: recording=True, start_time=%.2f" % start_time)

    def stop_recording(self) -> float:
        """标记结束录音，返回持续秒数"""
        duration = 0.0
        if self.recording_start_time > 0:
            duration = time.time() - self.recording_start_time

        self.recording = False
        self.recording_start_time = 0.0
        logger.debug("录音状态已更新: recording=False, duration=%.2fs" % duration)
        return duration

    @property
    def is_connected(self) -> bool:
        """检查 WebSocket 是否已连接"""
        if self.websocket is None:
            return False
        try:
            return not self.websocket.closed
        except AttributeError:
            # websockets 新版 API 无 closed 属性
            return self.websocket.state.name == 'OPEN' if hasattr(self.websocket, 'state') else True

    def register_audio_file(self, task_id: str, file_path: Path) -> None:
        """注册任务对应的音频文件"""
        self.audio_files[task_id] = file_path

    def pop_audio_file(self, task_id: str) -> Optional[Path]:
        """取出并移除任务对应的音频文件路径"""
        return self.audio_files.pop(task_id, None)

    def set_output_text(self, text: str) -> None:
        """记录最近一次输出文本"""
        self.last_output_text = text
