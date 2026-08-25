# coding: utf-8
"""
音频文件管理模块（自 core/client/audio/file_manager.py 移植）

管理录音文件生命周期：创建（MP3 需 FFmpeg / WAV 兜底）、写入、完成、重命名。
"""

from __future__ import annotations

import re
import shutil
import tempfile
import time
import wave
from os import makedirs
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen
from typing import Optional, Tuple, Union

import numpy as np

from config_client import ClientConfig as Config
from cw_linux.logger import get_logger

logger = get_logger('client')

# 音频文件句柄类型
AudioWriter = Union[Popen, wave.Wave_write]


class AudioFileManager:
    """
    音频文件管理器

    检测到 FFmpeg 时保存 MP3，否则保存 WAV。
    """

    SAMPLE_RATE = 48000

    def __init__(self):
        self.file_path: Optional[Path] = None
        self.file_handle: Optional[AudioWriter] = None
        self.channels: int = 1
        self._has_ffmpeg = shutil.which('ffmpeg') is not None

        if self._has_ffmpeg:
            logger.debug("检测到 FFmpeg，将使用 MP3 格式保存录音")
        else:
            logger.debug("未检测到 FFmpeg，将使用 WAV 格式保存录音")

    def create(self, channels: int, time_start: float) -> Tuple[Path, AudioWriter]:
        """
        创建音频文件

        Args:
            channels: 声道数
            time_start: 录音开始时间戳
        """
        self.channels = channels

        local_time = time.localtime(time_start)
        time_year = time.strftime('%Y', local_time)
        time_month = time.strftime('%m', local_time)
        time_ymdhms = time.strftime("%Y%m%d-%H%M%S", local_time)

        folder_path = Path() / time_year / time_month / 'assets'
        makedirs(folder_path, exist_ok=True)

        file_path = tempfile.mktemp(prefix='(%s)' % time_ymdhms, dir=folder_path)
        file_path = Path(file_path)

        if self._has_ffmpeg:
            file_path = file_path.with_suffix('.mp3')
            ffmpeg_command = [
                'ffmpeg', '-y',
                '-f', 'f32le',
                '-ar', str(self.SAMPLE_RATE),
                '-ac', str(channels),
                '-i', '-',
                '-b:a', '192k',
                str(file_path),
            ]
            file_handle = Popen(ffmpeg_command, stdin=PIPE, stdout=DEVNULL, stderr=DEVNULL)
        else:
            file_path = file_path.with_suffix('.wav')
            file_handle = wave.open(str(file_path), 'w')
            file_handle.setnchannels(channels)
            file_handle.setsampwidth(2)  # 16-bit
            file_handle.setframerate(self.SAMPLE_RATE)

        logger.debug("创建音频文件: %s" % file_path)

        self.file_path = file_path
        self.file_handle = file_handle

        return file_path, file_handle

    def write(self, data: np.ndarray) -> None:
        """写入 float32 音频数据"""
        if self.file_handle is None:
            return

        try:
            if isinstance(self.file_handle, Popen):
                self.file_handle.stdin.write(data.tobytes())
                self.file_handle.stdin.flush()
            else:
                int_data = (data * (2 ** 15 - 1)).astype(np.int16).tobytes()
                self.file_handle.writeframes(int_data)
        except Exception as e:
            logger.warning("写入录音数据失败: %s" % e)

    def finish(self) -> Optional[Path]:
        """结束写入并关闭文件"""
        if self.file_handle is None:
            return self.file_path

        try:
            if isinstance(self.file_handle, Popen):
                self.file_handle.stdin.close()
                self.file_handle.wait()
            else:
                self.file_handle.close()
        except Exception as e:
            logger.error("关闭音频文件时发生错误: %s" % e)
        finally:
            self.file_handle = None

        return self.file_path

    def discard(self) -> None:
        """丢弃本次录音（任务取消时调用）"""
        try:
            if isinstance(self.file_handle, Popen):
                self.file_handle.kill()
            elif self.file_handle is not None:
                self.file_handle.close()
        except Exception:
            pass
        finally:
            self.file_handle = None

        if self.file_path and self.file_path.exists():
            try:
                self.file_path.unlink()
                logger.debug("已删除取消任务的录音文件: %s" % self.file_path)
            except Exception as e:
                logger.debug("删除录音文件失败: %s" % e)
            self.file_path = None

    def rename(self, text: str, time_start: float) -> Optional[Path]:
        """根据识别文本重命名录音文件"""
        if self.file_path is None or not self.file_path.exists():
            return None

        time_ymdhms = time.strftime("%Y%m%d-%H%M%S", time.localtime(time_start))

        # 截取文本并清理文件名非法字符
        text_clean = text[:Config.audio_name_len]
        text_clean = re.sub(r'[\\/:\"*?<>|]', ' ', text_clean).strip()

        file_stem = '(%s)%s' % (time_ymdhms, text_clean)
        new_path = self.file_path.with_name(file_stem + self.file_path.suffix)

        try:
            self.file_path.rename(new_path)
            logger.debug("音频文件已重命名: %s -> %s" % (self.file_path.name, new_path.name))
            self.file_path = new_path
            return new_path
        except Exception as e:
            logger.error("重命名音频文件失败: %s" % e)
            return self.file_path
