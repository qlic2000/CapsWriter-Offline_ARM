# coding: utf-8
"""
快捷键任务模块（自 core/client/shortcut/task.py 移植）

跟踪单个快捷键的录音任务状态。
"""

from __future__ import annotations

import asyncio
import time
from threading import Event
from typing import TYPE_CHECKING, Optional

from cw_linux.logger import get_logger

if TYPE_CHECKING:
    from config_client import Shortcut
    from cw_linux.state import ClientState
    from cw_linux.audio.recorder import AudioRecorder
    from cw_linux.app import CapsWriterClient

logger = get_logger('client')


class HotkeyTask:
    """
    单个快捷键的录音任务

    与 Windows 版 ShortcutTask 语义一致：
    - launch(): 开始录音（向队列发 begin，启动 AudioRecorder）
    - finish(): 完成录音（向队列发 finish）
    - cancel(): 取消录音（时间过短误触）
    """

    def __init__(self, app: 'CapsWriterClient', shortcut: 'Shortcut'):
        self.app = app
        self.shortcut = shortcut

        self.task: Optional[asyncio.Future] = None
        self.recording_start_time: float = 0.0
        self.is_recording: bool = False

        # 单击模式状态
        self.pressed: bool = False
        self.released: bool = True
        self.event: Event = Event()

        # 阈值（秒）
        self.threshold: float = 0.3

    @property
    def state(self) -> 'ClientState':
        return self.app.state

    def _get_recorder(self) -> 'AudioRecorder':
        from cw_linux.audio.recorder import AudioRecorder
        return AudioRecorder(self.app)

    def launch(self) -> None:
        """开始录音"""
        logger.info("[%s] 触发：开始录音" % self.shortcut['key'])

        self.recording_start_time = time.time()
        self.is_recording = True

        asyncio.run_coroutine_threadsafe(
            self.state.queue_in.put({'type': 'begin', 'time': self.recording_start_time, 'data': None}),
            self.app.loop
        )

        self.state.start_recording(self.recording_start_time)

        recorder = self._get_recorder()
        self.task = asyncio.run_coroutine_threadsafe(
            recorder.record_and_send(),
            self.app.loop,
        )

    def cancel(self) -> None:
        """取消录音任务（时间过短）"""
        logger.debug("[%s] 取消录音任务（时间过短）" % self.shortcut['key'])

        self.is_recording = False
        self.state.stop_recording()

        if self.task is not None:
            self.task.cancel()
            self.task = None

    def finish(self) -> None:
        """完成录音"""
        logger.info("[%s] 释放：完成录音" % self.shortcut['key'])

        self.is_recording = False
        self.state.stop_recording()

        asyncio.run_coroutine_threadsafe(
            self.state.queue_in.put({
                'type': 'finish',
                'time': time.time(),
                'data': None
            }),
            self.app.loop
        )
