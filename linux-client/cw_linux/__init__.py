# coding: utf-8
"""
cw_linux — CapsWriter Offline Linux 客户端核心包

从 Windows 客户端 (core/client) 精简移植，适配 arm64 银河麒麟 V10：
- 保留：WebSocket 通信、录音、热词替换、规则替换、文本上屏、日记归档、文件转录
- 移除：LLM 润色、系统托盘、Toast 弹窗、UDP 广播/控制、鼠标侧键
"""

import colorama

colorama.init()

from cw_linux.logger import get_logger, setup_logger

__version__ = '2.6-linux.1'

__all__ = ['get_logger', 'setup_logger', '__version__']
