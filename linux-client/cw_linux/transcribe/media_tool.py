# coding: utf-8
"""
媒体工具（自 core/client/transcribe/media_tool.py 移植）

FFmpeg 环境检测、音频时长获取、提取命令构建。
"""

import asyncio
import shutil
from typing import List

from cw_linux.state import console
from cw_linux.logger import get_logger

logger = get_logger('client')


class MediaTool:
    """FFmpeg 相关操作"""

    @staticmethod
    def check_environment() -> bool:
        """检查 FFmpeg 与 ffprobe 是否可用"""
        if shutil.which('ffmpeg') is None:
            console.print('[bold red]错误：未检测到 FFmpeg[/bold red]')
            console.print('    文件转录依赖 FFmpeg 提取音视频中的音频。')
            console.print('    麒麟 V10 可执行: sudo yum install ffmpeg 或使用离线 rpm 包安装。\n')
            logger.error("未检测到 FFmpeg 环境，无法进行文件转录")
            return False

        if shutil.which('ffprobe') is None:
            console.print('[yellow]提示：未检测到 ffprobe，进度显示将不可用[/yellow]')
            logger.warning("未检测到 ffprobe")

        return True

    @staticmethod
    async def get_audio_duration(file) -> float:
        """通过 ffprobe 获取音频时长，失败返回 0"""
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(file)
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                return float(stdout.decode().strip())
        except Exception as e:
            logger.warning("无法通过 ffprobe 获取时长: %s" % e)
        return 0.0

    @staticmethod
    def build_ffmpeg_cmd(file) -> List[str]:
        """构建提取 16kHz 单声道 float32 音频的 FFmpeg 命令"""
        return [
            "ffmpeg", "-i", str(file),
            "-f", "f32le", "-ac", "1", "-ar", "16000", "-"
        ]
