# coding: utf-8
"""
Linux 快捷键管理器

替代 Windows 版基于 win32_event_filter 的 ShortcutManager：

- X11 图形会话：使用 pynput keyboard.Listener 全局监听。
  suppress=True 时通过 listener.suppress_event() 阻塞原按键，
  短按（<阈值）时自动补发按键，保证 CapsLock 原有功能不受影响；
  Wayland 下无法阻塞，请将配置中 suppress 设为 False。
- 无图形环境（SSH/TTY）：提供 terminal 类型快捷键，
  在终端按回车开始说话、再次回车结束。

事件处理语义与 Windows 版 ShortcutEventHandler 一致：
- hold_mode：按下即录，松开判定时长，短于阈值取消并补发按键
- click_mode：单击开始，再击结束
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from cw_linux.logger import get_logger

if TYPE_CHECKING:
    from config_client import ClientConfig as ConfigModule
    from cw_linux.app import CapsWriterClient

logger = get_logger('client')

# pynput 按键名称映射（配置名 -> pynput Key 属性）
_SPECIAL_KEY_MAP = {
    'caps_lock': 'caps_lock',
    'num_lock': 'num_lock',
    'scroll_lock': 'scroll_lock',
    'space': 'space',
    'enter': 'enter',
    'tab': 'tab',
    'esc': 'esc',
    'backspace': 'backspace',
    'delete': 'delete',
    'insert': 'insert',
    'home': 'home',
    'end': 'end',
    'page_up': 'page_up',
    'page_down': 'page_down',
    'print_screen': 'print_screen',
    'pause': 'pause',
    'menu': 'menu',
    'up': 'up',
    'down': 'down',
    'left': 'left',
    'right': 'right',
}

# 可恢复状态的锁键（suppress=False 松开时需补发以还原状态）
_TOGGLE_KEYS = {'caps_lock', 'num_lock', 'scroll_lock'}


class HotkeyManager:
    """
    Linux 快捷键管理器

    Args:
        app: 客户端 App 实例
        shortcuts: 配置中的快捷键字典列表
    """

    def __init__(self, app: 'CapsWriterClient', shortcuts: List[dict]):
        self.app = app
        self.shortcuts = shortcuts

        self.keyboard_listener = None   # pynput keyboard.Listener
        self._terminal_thread = None    # 终端回退监听线程

        # key_name -> HotkeyTask
        self.tasks: Dict[str, HotkeyTask] = {}

        self._pool = ThreadPoolExecutor(max_workers=2)

        # 补发按键时的防自捕获标志
        self._restoring_keys = set()

        self._init_tasks()

    @property
    def state(self):
        return self.app.state

    def _init_tasks(self) -> None:
        from .task import HotkeyTask

        from config_client import ClientConfig as Config

        for shortcut in self.shortcuts:
            if not shortcut.get('enabled', True):
                continue

            task = HotkeyTask(self.app, shortcut)
            task.threshold = shortcut.get('threshold', Config.threshold)
            self.tasks[shortcut['key']] = task

    def _resolve_pynput_key(self, key_name: str):
        """将配置的按键名称解析为 pynput 键对象"""
        from pynput import keyboard

        if key_name in _SPECIAL_KEY_MAP:
            return getattr(keyboard.Key, _SPECIAL_KEY_MAP[key_name], None)

        if len(key_name) == 1:
            return keyboard.KeyCode.from_char(key_name)

        # f1-f24
        if key_name.startswith('f') and key_name[1:].isdigit():
            return getattr(keyboard.Key, key_name, None)

        return None

    def _key_to_name(self, key) -> Optional[str]:
        """将 pynput 按键事件对象转换为任务键名"""
        try:
            from pynput.keyboard import Key, KeyCode

            if isinstance(key, Key):
                for name, attr in _SPECIAL_KEY_MAP.items():
                    if getattr(Key, attr, None) == key:
                        return name
                # f1-f24
                name = key.name
                if name and name.startswith('f') and name[1:].isdigit():
                    return name
                return None

            if isinstance(key, KeyCode):
                if key.char:
                    return key.char.lower() if key.char.isalpha() else key.char
                if key.vk is not None:
                    return None
        except Exception:
            pass
        return None

    # ========== 事件处理 ==========

    def _handle_keydown(self, task: 'HotkeyTask') -> None:
        """按下事件"""
        if task.shortcut.get('hold_mode', True):
            if not task.is_recording:
                task.launch()
            return

        # 单击模式
        if task.released:
            task.pressed = True
            task.released = False
            task.event = __import__('threading').Event()
            self._pool.submit(self._count_down, task)
            self._pool.submit(self._manage_task, task)

    def _handle_keyup(self, task: 'HotkeyTask') -> None:
        """松开事件"""
        if task.shortcut.get('hold_mode', True):
            if not task.is_recording:
                return

            duration = time.time() - task.recording_start_time
            logger.debug("松开，持续时间: %.2fs" % duration)

            if duration < task.threshold:
                self._handle_short_press(task)
            else:
                task.finish()
            return

        # 单击模式松开
        if task.pressed:
            task.pressed = False
            task.released = True
            task.event.set()

    def _handle_short_press(self, task: 'HotkeyTask') -> None:
        """短按：取消录音并补发按键"""
        cancel_start = time.perf_counter()
        task.cancel()
        logger.debug("task.cancel() 耗时: %.2fms" % ((time.perf_counter() - cancel_start) * 1000))

        if task.shortcut.get('suppress', False):
            logger.debug("安排异步补发按键")
            self._pool.submit(self._emulate_key, task)

    def _count_down(self, task: 'HotkeyTask') -> None:
        """单击模式倒计时"""
        time.sleep(task.threshold)
        task.event.set()

    def _manage_task(self, task: 'HotkeyTask') -> None:
        """单击模式任务管理"""
        was_recording = task.is_recording

        if not was_recording:
            task.launch()

        if task.event.wait(timeout=task.threshold * 0.8):
            if task.is_recording and was_recording:
                task.finish()
        else:
            if not was_recording:
                task.cancel()

    def _emulate_key(self, task: 'HotkeyTask') -> None:
        """
        线程中补发按键（X11）

        通过 controller 发送，配合防自捕获标志避免再次触发录音。
        """
        key_name = task.shortcut['key']
        self._restoring_keys.add(key_name)

        try:
            time.sleep(0.05)

            from pynput import keyboard
            controller = keyboard.Controller()
            key_obj = self._resolve_pynput_key(key_name)
            if key_obj is not None:
                controller.press(key_obj)
                controller.release(key_obj)
                logger.debug("[%s] 补发按键成功" % key_name)
        except Exception as e:
            logger.warning("[%s] 补发按键失败: %s" % (key_name, e))
        finally:
            # 延迟清除标志，等待补发事件的回环消息
            time.sleep(0.15)
            self._restoring_keys.discard(key_name)

    # ========== 监听器 ==========

    def _make_x11_filter(self):
        """构造 pynput 全局键盘回调"""
        def on_press(key):
            key_name = self._key_to_name(key)
            if key_name is None or key_name not in self.tasks:
                return

            # 防自捕获：补发的按键不再触发
            if key_name in self._restoring_keys:
                return

            self._handle_keydown(self.tasks[key_name])

        def on_release(key):
            key_name = self._key_to_name(key)
            if key_name is None or key_name not in self.tasks:
                return

            if key_name in self._restoring_keys:
                continue_suppress = True
            else:
                continue_suppress = False
                self._handle_keyup(self.tasks[key_name])

            # 阻塞原按键
            task = self.tasks[key_name]
            if task.shortcut.get('suppress', False) and self.keyboard_listener:
                try:
                    self.keyboard_listener.suppress_event()
                except Exception:
                    pass

        return on_press, on_release

    def _start_keyboard_listener(self) -> bool:
        """启动 X11 全局键盘监听"""
        has_keyboard = any(
            s.get('type', 'keyboard') == 'keyboard'
            for s in self.shortcuts if s.get('enabled', True)
        )
        if not has_keyboard:
            return True

        try:
            from pynput import keyboard
        except Exception as e:
            logger.error("pynput 初始化失败: %s" % e)
            console_hint()
            return False

        on_press, on_release = self._make_x11_filter()

        try:
            self.keyboard_listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release,
            )
            self.keyboard_listener.start()
            logger.info("键盘全局监听已启动 (X11)")
            return True
        except Exception as e:
            err = str(e)
            logger.error("启动全局键盘监听失败: %s" % err)
            if 'DISPLAY' in err or 'display' in err.lower():
                console_hint_display()
            elif 'root' in err.lower() or 'permission' in err.lower():
                console_hint_permission()
            return False

    def _start_terminal_hotkey(self):
        """启动终端回退热键（回车说话）"""
        has_terminal = any(
            s.get('type') == 'terminal'
            for s in self.shortcuts if s.get('enabled', True)
        )
        if not has_terminal:
            return

        import threading

        def terminal_loop():
            task_key = next(
                s['key'] for s in self.shortcuts
                if s.get('type') == 'terminal' and s.get('enabled', True)
            )
            task = self.tasks.get(task_key)
            if task is None:
                return

            print('[CapsWriter] 终端模式：按回车开始录音，再次回车结束，Ctrl+C 退出')
            while True:
                try:
                    input()
                except EOFError:
                    break

                if task.is_recording:
                    task.finish()
                    print('[CapsWriter] 录音结束，识别中...')
                else:
                    task.launch()
                    print('[CapsWriter] 正在录音...')

        self._terminal_thread = threading.Thread(target=terminal_loop, daemon=True)
        self._terminal_thread.start()
        logger.info("终端回退热键已启用")

    def start(self) -> None:
        """启动所有监听器"""
        ok = self._start_keyboard_listener()
        self._start_terminal_hotkey()

        if ok:
            for shortcut in self.shortcuts:
                if shortcut.get('enabled', True):
                    mode = "长按" if shortcut.get('hold_mode', True) else "单击"
                    logger.info(
                        "  [%s] %s模式, 阻塞:%s (%s)" %
                        (shortcut['key'], mode, shortcut.get('suppress', False),
                         shortcut.get('type', 'keyboard'))
                    )

    def stop(self) -> None:
        """停止所有监听器"""
        if self.keyboard_listener:
            try:
                self.keyboard_listener.stop()
                logger.debug("键盘监听器已停止")
            except Exception:
                pass
            finally:
                self.keyboard_listener = None

        for task in self.tasks.values():
            if task.is_recording:
                task.cancel()

        self._pool.shutdown(wait=False)
        logger.debug("快捷键管理器线程池已关闭")


def console_hint():
    print("""
[bold red]无法启动全局键盘监听[/]

在 Linux 上需要图形会话（DISPLAY）或 root 权限。

解决方案：
  1. 在桌面环境中直接运行本程序（推荐）
  2. SSH 会话中请在 shortcuts 里加入 terminal 类型快捷键
  3. 安装依赖：pip3 install pynput
""")


def console_hint_display():
    print("""
未检测到图形会话 (DISPLAY/WAYLAND_DISPLAY)。

全局快捷键仅在图形会话中可用。若在 SSH/TTY 中运行，
请在 config_client.py 的 shortcuts 中添加：
  {'key': 'enter', 'type': 'terminal', 'hold_mode': False, 'enabled': True}
""")


def console_hint_permission():
    print("""
权限不足，无法监听键盘事件。

解决方法：
  1. 将当前用户加入 input 组： sudo usermod -aG input $USER 后重新登录
  2. 或使用 sudo 运行本程序
""")
