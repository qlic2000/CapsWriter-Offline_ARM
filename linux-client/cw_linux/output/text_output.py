# coding: utf-8
"""
文本输出模块（自 core/client/output/text_output.py 移植并适配 Linux）

- 打字方式：xdotool (X11) / wtype (Wayland)，工具缺失时降级为仅复制到剪贴板
- 粘贴方式：写剪贴板后模拟 Ctrl-V
"""

from __future__ import annotations

import re
import asyncio
from typing import Optional

from config_client import ClientConfig as Config
from cw_linux.logger import get_logger
from .clipboard import type_text, paste_via_clipboard, set_clipboard_text

logger = get_logger('client')

# 语义字符计数模式：中文字=1、英文单词=1、数字串=1
_SEMANTIC_UNIT_RE = re.compile(
    r'[一-鿿㐀-䶿豈-﫿]'
    r'|[a-zA-Z]+'
    r'|\d+'
)


def count_semantic_units(text: str) -> int:
    """计算语义字符数"""
    return len(_SEMANTIC_UNIT_RE.findall(text))


class TextOutput:
    """
    文本输出器

    支持模拟打字和粘贴两种输出方式。
    """

    @staticmethod
    def strip_punc(text: str) -> str:
        """
        消除末尾标点

        语义单元数不超过 trash_punc_thresh 时去除末尾标点。
        """
        if not text or not Config.trash_punc:
            return text

        if Config.trash_punc_thresh > 0 and count_semantic_units(text) > Config.trash_punc_thresh:
            return text

        return re.sub("(?<=.)[%s]$" % Config.trash_punc, "", text)

    async def output(self, text: str, paste: Optional[bool] = None) -> None:
        """
        输出识别结果到当前焦点窗口

        Args:
            text: 要输出的文本
            paste: 是否使用粘贴方式（None 表示使用配置值）
        """
        if not text:
            # 即使无文本也确保剪贴板可用（供手动粘贴场景）
            if paste is None or paste:
                set_clipboard_text('')
            return

        if paste is None:
            paste = Config.paste

        loop = asyncio.get_event_loop()

        if paste:
            await loop.run_in_executor(None, paste_via_clipboard, text, Config.restore_clip)
        else:
            tool = getattr(Config.linux, 'type_tool', 'auto')
            ok = await loop.run_in_executor(None, type_text, text, tool)
            if not ok:
                # 输入工具不可用时，将结果放入剪贴板兜底
                logger.info("已将识别结果复制到剪贴板")
                await loop.run_in_executor(None, set_clipboard_text, text)
