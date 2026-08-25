# coding: utf-8
"""
output 子模块：结果处理器、文本输出、剪贴板
"""

from .text_output import TextOutput
from .clipboard import (
    get_clipboard_text,
    set_clipboard_text,
    safe_paste,
    safe_copy,
    copy_to_clipboard,
)

__all__ = [
    'TextOutput',
    'get_clipboard_text',
    'set_clipboard_text',
    'safe_paste',
    'safe_copy',
    'copy_to_clipboard',
]
