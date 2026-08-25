# coding: utf-8
"""
录音模块（自 core/client/audio/recorder.py 移植，逻辑保持一致）

从队列读取音频块，超过阈值后边录边发，松开后发送结束标志。
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from typing import TYPE_CHECKING, Optional

import numpy as np

from config_client import ClientConfig as Config
from cw_linux.state import console
from cw_linux.audio.file_manager import AudioFileManager
from cw_linux.protocol import AudioMessage
from cw_linux.logger import get_logger

if TYPE_CHECKING:
    from cw_linux.state import ClientState
    from cw_linux.app import CapsWriterClient

logger = get_logger('client')


class AudioRecorder:
    """
    音频录制器：管理一次完整的录音会话
    """

    def __init__(self, app: 'CapsWriterClient'):
        self.app = app
        self.task_id: Optional[str] = None
        self._file_manager: Optional[AudioFileManager] = None
        self._start_time: float = 0.0
        self._duration: float = 0.0
        self._cache: list = []

    @property
    def state(self) -> 'ClientState':
        return self.app.state

    def _make_message(self, data: str, is_final: bool) -> AudioMessage:
        """构造与 Windows 服务端兼容的 AudioMessage"""
        return AudioMessage(
            task_id=self.task_id,
            source='mic',
            data=data,
            is_final=is_final,
            time_start=self._start_time,
            seg_duration=Config.mic_seg_duration,
            seg_overlap=Config.mic_seg_overlap,
            context=Config.context,
            language=Config.language,
        )

    async def _send_message(self, message: AudioMessage) -> None:
        """发送消息到服务端"""
        if not self.app.ws.is_connected:
            if message.is_final:
                self.state.pop_audio_file(message.task_id)
                console.print('    服务端未连接，无法发送\n')
                logger.warning("服务端未连接，无法发送音频数据")
            return

        try:
            success = await self.app.ws.send(message)
            if not success and message.is_final:
                self.state.pop_audio_file(message.task_id)
        except Exception as e:
            logger.debug("发送失败: %s" % e)

    async def record_and_send(self) -> None:
        """
        录音并发送数据（在事件循环中运行）

        队列任务类型：
        - begin  : 录音开始
        - data   : 音频块 (float32 ndarray)
        - finish : 结束标志
        """
        try:
            self.task_id = str(uuid.uuid1())
            logger.debug("创建录音任务，任务ID: %s" % self.task_id)

            self._start_time = 0.0
            self._duration = 0.0
            self._cache = []

            file_path = None
            if Config.save_audio:
                self._file_manager = AudioFileManager()

            while True:
                task = await self.state.queue_in.get()
                self.state.queue_in.task_done()

                if not task:
                    break

                if task['type'] == 'begin':
                    self._start_time = task['time']
                    logger.debug("录音开始，时间戳: %s" % self._start_time)

                elif task['type'] == 'data':
                    # 阈值之前的音频先积攒，防止误触
                    if task['time'] - self._start_time < Config.threshold:
                        self._cache.append(task['data'])
                        continue

                    # 超过阈值后创建本地录音文件
                    if Config.save_audio and self._file_manager and file_path is None:
                        file_path, _ = self._file_manager.create(
                            task['data'].shape[1],
                            self._start_time
                        )
                        self.state.register_audio_file(self.task_id, file_path)

                    # 合并缓存
                    if self._cache:
                        data = np.concatenate(self._cache)
                        self._cache.clear()
                    else:
                        data = task['data']

                    self._duration += len(data) / 48000
                    if Config.save_audio and self._file_manager:
                        self._file_manager.write(data)

                    # 立体声转单声道并降采样到 16k（每3个样本取均值点）
                    message = self._make_message(
                        base64.b64encode(
                            np.mean(data[::3], axis=1).tobytes()
                        ).decode('utf-8'),
                        is_final=False,
                    )
                    asyncio.create_task(self._send_message(message))

                elif task['type'] == 'finish':
                    # 发送缓存中剩余的音频
                    if self._cache:
                        data = np.concatenate(self._cache)
                        self._cache.clear()

                        self._duration += len(data) / 48000
                        if Config.save_audio and self._file_manager:
                            self._file_manager.write(data)

                        message = self._make_message(
                            base64.b64encode(
                                np.mean(data[::3], axis=1).tobytes()
                            ).decode('utf-8'),
                            is_final=False,
                        )
                        asyncio.create_task(self._send_message(message))

                    if Config.save_audio and self._file_manager:
                        self._file_manager.finish()
                        logger.debug("完成音频文件写入")

                    console.print('任务标识：%s' % self.task_id)
                    console.print('    录音时长：%.2fs' % self._duration)
                    logger.info("录音任务完成，任务ID: %s, 时长: %.2fs" % (self.task_id, self._duration))

                    # 通知服务端结束
                    message = self._make_message('', is_final=True)
                    asyncio.create_task(self._send_message(message))
                    break

        except asyncio.CancelledError:
            # 短按取消：丢弃本次会话
            if Config.save_audio and self._file_manager:
                try:
                    self._file_manager.discard()
                except Exception:
                    pass
            logger.debug("录音任务已取消")

        except Exception as e:
            logger.error("录音任务错误: %s" % e, exc_info=True)
