# coding: utf-8
"""
文件转录器（自 core/client/transcribe/file_transcriber.py 精简移植）

流程：检查环境 -> FFmpeg 提取音频流 -> WebSocket 发送 ->
等待最终结果 -> 应用热词/规则替换 -> 保存 srt/txt/json。
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from config_client import ClientConfig as Config
from cw_linux.state import console
from cw_linux.protocol import AudioMessage, RecognitionMessage
from .media_tool import MediaTool
from .result_handler import ResultHandler
from cw_linux.logger import get_logger

if TYPE_CHECKING:
    from cw_linux.app import CapsWriterClient

logger = get_logger('client')


class FileTranscriber:
    """文件转录器：协调单文件的转录流程"""

    def __init__(self, app: 'CapsWriterClient', file: Path):
        self.app = app
        self.file = file
        self.task_id: Optional[str] = None
        self._audio_duration: float = 0.0

    @property
    def _ws_manager(self):
        return self.app.ws

    async def check(self) -> bool:
        """转录前检查：文件存在、FFmpeg 可用、服务端可连接"""
        if not self.file.exists():
            logger.error("文件不存在: %s" % self.file)
            return False

        if not MediaTool.check_environment():
            return False

        if not await self._ws_manager.connect():
            logger.error("无法连接到服务端")
            console.print('[bold red]无法连接服务端，请检查 config_client.py 中 addr 配置[/bold red]')
            return False

        return True

    async def send(self) -> None:
        """FFmpeg 提取音频并流式发送到服务端"""
        self.task_id = str(uuid.uuid1())
        console.print('\n任务标识：%s' % self.task_id)
        console.print('    处理文件：%s' % self.file)

        self._audio_duration = await MediaTool.get_audio_duration(self.file)
        if self._audio_duration > 0:
            console.print('    音频长度：%.2fs' % self._audio_duration)

        logger.info("开始转录文件: %s, 任务ID: %s" % (self.file, self.task_id))

        ffmpeg_cmd = MediaTool.build_ffmpeg_cmd(self.file)
        process = None

        try:
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )

            # 每块 1 分钟音频（16000 * 4字节 * 60秒）
            chunk_size = 16000 * 4 * 60
            bytes_sent = 0

            while True:
                data = await process.stdout.read(chunk_size)
                if not data:
                    break

                bytes_sent += len(data)
                progress = bytes_sent / 4 / 16000
                if self._audio_duration > 0:
                    prog_str = '    发送进度：%.2fs / %.2fs' % (progress, self._audio_duration)
                else:
                    prog_str = '    发送进度：%.2fs' % progress
                console.print(prog_str, end='\r')

                message = AudioMessage(
                    task_id=self.task_id,
                    source='file',
                    data=base64.b64encode(data).decode('utf-8'),
                    is_final=False,
                    time_start=time.time(),
                    seg_duration=Config.file_seg_duration,
                    seg_overlap=Config.file_seg_overlap,
                    context=Config.context,
                    language=Config.language,
                )
                if not await self._ws_manager.send(message):
                    raise ConnectionError("消息发送失败，连接可能已断开")

            final_message = AudioMessage(
                task_id=self.task_id,
                source='file',
                data='',
                is_final=True,
                time_start=time.time(),
                seg_duration=Config.file_seg_duration,
                seg_overlap=Config.file_seg_overlap,
                context=Config.context,
                language=Config.language,
            )
            if not await self._ws_manager.send(final_message):
                raise ConnectionError("结束标志发送失败")

            await process.wait()

            if self._audio_duration == 0 and bytes_sent > 0:
                self._audio_duration = bytes_sent / 4 / 16000
                console.print('\n    音频长度：%.2fs' % self._audio_duration)

            logger.debug("音频数据发送完成")

        except Exception as e:
            logger.error("转录发送异常: %s" % e, exc_info=True)
            if process is not None and process.returncode is None:
                process.terminate()

    async def receive(self) -> None:
        """接收最终识别结果并保存"""
        message = None

        try:
            while True:
                msg = await self._ws_manager.receive()
                if msg is None:
                    break

                console.print('    转录进度: %.2fs' % msg.duration, end='\r')
                if msg.is_final:
                    message = msg
                    break
        except Exception as e:
            logger.error("接收消息错误: %s" % e)
            return

        if message is None:
            logger.warning("未收到最终结果")
            return

        self._apply_hotwords(message)

        text_display = ResultHandler.save_results(self.file, message)

        process_duration = message.time_complete - message.time_start
        console.print('\033[K    处理耗时：%.2fs' % process_duration)
        console.print('    识别结果：\n[green]%s' % text_display)

        logger.info(
            "转录完成: %s, 处理耗时: %.2fs, 文本长度: %d" %
            (self.file, process_duration, len(text_display))
        )

    def _apply_hotwords(self, message: RecognitionMessage) -> None:
        """对识别结果应用热词与规则替换"""
        text_accu = message.text_accu or message.text
        corrected = text_accu

        # 1. 音素热词替换
        if Config.hot:
            correction = self.app.hotword.get_phoneme_corrector().correct(text_accu, k=10)
            corrected = correction.text
            for origin, hw, score in correction.matches:
                logger.info("热词匹配: 「%s」→「%s」(分数=%.2f)" % (origin, hw, score))
                console.print('    [cyan]热词匹配:[/] 「%s」→「[green]%s[/]」(分数=%.2f)' %
                              (origin, hw, score))

        # 2. 规则替换
        if Config.hot_rule:
            corrected = self.app.hotword.get_rule_corrector().substitute(corrected)

        # 3. 有变化则同步回 message
        if corrected != text_accu:
            message.text_accu = corrected
            message.text = corrected
            logger.debug("热词修正完成")

    async def close(self) -> None:
        """关闭 WebSocket 连接"""
        try:
            await self._ws_manager.close()
        except Exception:
            pass
