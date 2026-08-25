# coding: utf-8
"""
音频流管理模块（自 core/client/audio/stream.py 移植并适配 Linux）

- 后端选择：PulseAudio（默认）失败时回退 ALSA
- 48000Hz float32 输入流，50ms 块
- 录音状态下通过 run_coroutine_threadsafe 将数据块推入异步队列
"""

from __future__ import annotations

import sys
import time
import threading
import asyncio
from typing import TYPE_CHECKING, Optional

import numpy as np

try:
    import sounddevice as sd
except OSError as _sd_err:
    # 系统缺少 libportaudio 时允许程序继续运行（文件转录不受影响）
    sd = None
    _SD_IMPORT_ERROR = _sd_err
else:
    _SD_IMPORT_ERROR = None

from config_client import ClientConfig as Config
from cw_linux.state import console
from cw_linux.logger import get_logger

if TYPE_CHECKING:
    from cw_linux.state import ClientState
    from ..app import CapsWriterClient

logger = get_logger('client')


class AudioStreamManager:
    """
    音频输入流管理器（Linux 版）

    Attributes:
        state: 客户端状态实例
        sample_rate: 采样率（48000Hz）
        block_duration: 每个数据块的时长（0.05s）
    """

    SAMPLE_RATE = 48000
    BLOCK_DURATION = 0.05  # 50ms

    def __init__(self, app: 'CapsWriterClient'):
        self.app = app
        self._channels = 1
        self._running = False
        self._api_name = None

    @property
    def state(self) -> 'ClientState':
        return self.app.state

    def _pick_hostapi(self) -> Optional[int]:
        """
        根据配置挑选音频后端：优先 PulseAudio，回退 ALSA

        Returns:
            HostApi 索引，找不到返回 None（使用默认）
        """
        if sd is None:
            return None

        api_pref = getattr(getattr(Config, 'linux', None), 'audio_api', 'auto')
        if api_pref == 'auto':
            return None  # 让 PortAudio 用系统默认后端

        try:
            apis = sd.query_hostapis()
            for i, api in enumerate(apis):
                name = api.get('name', '')
                if api_pref.lower() in name.lower():
                    logger.debug("使用音频后端: %s" % name)
                    return i
        except Exception as e:
            logger.warning("枚举音频后端失败: %s" % e)
        return None

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        """音频回调：仅在录音状态时将数据块推入队列"""
        if status:
            logger.debug("音频回调状态: %s" % status)

        if not self.state.recording:
            return

        if self.app.loop and self.state.queue_in:
            asyncio.run_coroutine_threadsafe(
                self.state.queue_in.put({
                    'type': 'data',
                    'time': time.time(),
                    'data': indata.copy(),
                }),
                self.app.loop
            )

    def _on_stream_finished(self) -> None:
        """音频流意外结束时的重启回调"""
        if not threading.main_thread().is_alive():
            return
        if not self._running:
            return

        logger.info("音频流意外结束，正在尝试重启...")
        self.reopen()

    def start(self) -> Optional[sd.InputStream]:
        """启动音频流"""
        if sd is None:
            logger.error("sounddevice 不可用（缺少 libportaudio）: %s" % _SD_IMPORT_ERROR)
            console.print('[bold red]无法初始化音频：系统缺少 PortAudio 库[/bold red]')
            console.print('请安装: sudo yum install portaudio-devel 后重新运行\n')
            return None

        if self._running:
            return self.state.stream

        device_index = getattr(getattr(Config, 'linux', None), 'input_device', None)
        hostapi = self._pick_hostapi()

        # 检测默认输入设备
        try:
            device = sd.query_devices(kind='input')
            self._channels = min(2, int(device['max_input_channels']) or 1)
            device_name = device.get('name', '未知设备')
            console.print(
                '使用默认音频设备：%s，声道数：%s' % (device_name, self._channels),
                end='\n\n'
            )
            logger.info("找到音频设备: %s, 声道数: %s" % (device_name, self._channels))
        except Exception as e:
            logger.error("未找到可用的麦克风设备: %s" % e)
            console.print('[bold red]未找到麦克风设备，请检查音频设备连接[/bold red]')
            return None

        stream_kwargs = dict(
            samplerate=self.SAMPLE_RATE,
            blocksize=int(self.BLOCK_DURATION * self.SAMPLE_RATE),
            dtype="float32",
            channels=self._channels,
            callback=self._audio_callback,
            finished_callback=self._on_stream_finished,
        )

        # 设备选择：显式配置 或 指定后端下的默认设备
        if isinstance(device_index, int):
            stream_kwargs['device'] = device_index
        else:
            stream_kwargs['device'] = None
        if hostapi is not None and device_index is None:
            stream_kwargs['device'] = (hostapi, None) if False else None
            # sounddevice 支持 device=(hostapi, None) 选择后端默认设备
            stream_kwargs['device'] = (hostapi,)

        try:
            stream = sd.InputStream(**stream_kwargs)
            stream.start()

            self.state.stream = stream
            self._running = True
            logger.debug(
                "音频流已启动: 采样率=%s, 块大小=%s" %
                (self.SAMPLE_RATE, int(self.BLOCK_DURATION * self.SAMPLE_RATE))
            )
            return stream

        except sd.PortAudioError as e:
            logger.error("创建音频流失败: %s" % e, exc_info=True)
            msg = str(e)
            console.print('[bold red]创建音频流失败[/bold red]')
            if 'Device unavailable' in msg or '-9985' in msg or '-9996' in msg:
                console.print("""
可能的原因与解决方法：

  1. 未检测到输入设备：请插入 USB 麦克风或检查 3.5mm 麦克风。
  2. PulseAudio 未运行：执行 `pulseaudio --start` 后重试，
     或将 config_client.py 中 linux.audio_api 改为 'alsa'。
  3. 用户不在 audio 组（无设备权限）：
     `sudo usermod -aG audio $USER` 后重新登录。
  4. 设备被独占占用：关闭其他录音程序后重试。
""")
            return None
        except Exception as e:
            logger.error("创建音频流失败: %s" % e, exc_info=True)
            return None

    def stop(self) -> None:
        """停止音频流"""
        if not self._running:
            return

        self._running = False
        if self.state.stream is not None:
            try:
                self.state.stream.close()
                logger.debug("音频流已停止")
            except Exception as e:
                logger.debug("停止音频流时发生错误: %s" % e)
            finally:
                self.state.stream = None

    def reopen(self) -> Optional[sd.InputStream]:
        """重新加载 PortAudio 并重启音频流"""
        logger.info("正在重启音频流...")

        self.stop()

        if sd is None:
            return None

        try:
            sd._terminate()
            sd._ffi.dlclose(sd._lib)
            sd._lib = sd._ffi.dlopen(sd._libname)
            sd._initialize()
        except Exception as e:
            logger.warning("重载 PortAudio 时发生警告: %s" % e)

        time.sleep(0.1)
        return self.start()
