# coding: utf-8
"""
audio 子模块：音频流、录音器、录音文件管理
"""

from cw_linux.logger import get_logger
from .recorder import AudioRecorder
from .stream import AudioStreamManager
from .file_manager import AudioFileManager

logger = get_logger('client')

__all__ = [
    'logger',
    'AudioRecorder',
    'AudioStreamManager',
    'AudioFileManager',
]
