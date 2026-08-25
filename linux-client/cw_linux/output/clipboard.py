# coding: utf-8
"""
剪贴板工具模块（替代 Windows 版 pyclip 依赖）

自动探测可用工具：wl-copy/wl-paste (Wayland) -> xclip -> xsel。
全部不可用时安全降级（返回空串/False），不影响主流程。
"""

import shutil
import subprocess
from typing import Optional

from cw_linux.logger import get_logger

logger = get_logger('client')

# 工具探测缓存
_clip_tool = None
_paste_tool = None
_checked = False


def _detect_tools() -> None:
    """探测系统可用的剪贴板命令行工具"""
    global _clip_tool, _paste_tool, _checked
    if _checked:
        return
    _checked = True

    if shutil.which('xclip'):
        _clip_tool = ('xclip', ['xclip', '-selection', 'clipboard'])
        _paste_tool = ('xclip', ['xclip', '-selection', 'clipboard', '-o'])
    elif shutil.which('xsel'):
        _clip_tool = ('xsel', ['xsel', '--clipboard', '--input'])
        _paste_tool = ('xsel', ['xsel', '--clipboard', '--output'])

    # Wayland 工具优先级更高（存在时覆盖）
    if shutil.which('wl-copy') and shutil.which('wl-paste'):
        _clip_tool = ('wl-copy', ['wl-copy'])
        _paste_tool = ('wl-paste', ['wl-paste', '--no-newline'])

    logger.debug(
        "剪贴板工具: copy=%s paste=%s" %
        (_clip_tool[0] if _clip_tool else None, _paste_tool[0] if _paste_tool else None)
    )


def get_clipboard_text() -> str:
    """
    读取剪贴板文本

    Returns:
        剪贴板内容，失败返回空字符串
    """
    _detect_tools()
    if _paste_tool is None:
        return ""

    try:
        result = subprocess.run(
            _paste_tool[1],
            capture_output=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.decode('utf-8', errors='replace')
    except Exception as e:
        logger.warning("读取剪贴板失败: %s" % e)
    return ""


def set_clipboard_text(content: str) -> bool:
    """
    写入剪贴板文本

    Args:
        content: 要写入的内容

    Returns:
        是否成功
    """
    if not content:
        return False

    _detect_tools()
    if _clip_tool is None:
        logger.warning("未找到 xclip/xsel/wl-copy，无法操作剪贴板")
        return False

    try:
        result = subprocess.run(
            _clip_tool[1],
            input=content.encode('utf-8'),
            timeout=2,
        )
        return result.returncode == 0
    except Exception as e:
        logger.warning("写入剪贴板失败: %s" % e)
        return False


def safe_paste() -> str:
    """兼容旧 API：读取剪贴板"""
    return get_clipboard_text()


def safe_copy(content) -> bool:
    """兼容旧 API：写入剪贴板"""
    if isinstance(content, bytes):
        try:
            content = content.decode('utf-8')
        except Exception:
            content = ''
    return set_clipboard_text(content)


def copy_to_clipboard(content: str):
    """复制内容到剪贴板（兼容旧 API）"""
    safe_copy(content)


def type_text(text: str, tool: str = 'auto') -> bool:
    """
    将文本模拟键入到当前焦点窗口

    优先 wtype (Wayland)，回退 xdotool type (X11)。

    Args:
        text: 要输入的文本
        tool: 'auto' | 'wtype' | 'xdotool'

    Returns:
        是否成功
    """
    def try_run(cmd_name, args):
        exe = shutil.which(cmd_name)
        if exe is None:
            return False
        try:
            subprocess.run(args, timeout=5)
            return True
        except Exception as e:
            logger.warning("%s 输入失败: %s" % (cmd_name, e))
            return False

    order = []
    if tool == 'auto':
        order = [('xdotool', ['xdotool', 'type', '--clearmodifiers', '--delay', '15', text]),
                 ('wtype', ['wtype', '-d', '15', text])]
    elif tool in ('xdotool', 'wtype'):
        cmd = {'xdotool': ['xdotool', 'type', '--clearmodifiers', '--delay', '15', text],
               'wtype': ['wtype', '-d', '15', text]}[tool]
        order = [(tool, cmd)]

    for name, args in order:
        if try_run(name, args):
            return True

    logger.warning("未找到可用的文字输入工具 (xdotool/wtype)，仅保留识别结果输出")
    return False


def paste_via_clipboard(text: str, restore: bool = True) -> bool:
    """
    通过 剪贴板+模拟Ctrl-V 粘贴文本

    Args:
        text: 要粘贴的文本
        restore: 是否恢复原剪贴板内容

    Returns:
        是否成功
    """
    original = get_clipboard_text()

    if not set_clipboard_text(text):
        return False

    sent = False
    try:
        from pynput.keyboard import Controller, Key
        controller = Controller()
        with controller.pressed(Key.ctrl):
            controller.tap('v')
        sent = True
    except Exception as e:
        logger.warning("模拟 Ctrl-V 失败: %s" % e)

    if restore and original:
        import time
        time.sleep(0.1)
        set_clipboard_text(original)

    return sent
