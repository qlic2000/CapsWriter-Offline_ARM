# coding: utf-8
"""
热词管理模块（自 core/client/hotword/manager.py 移植）

差异：文件监视由 watchdog Observer 改为轻量轮询线程，
避免 watchdog 在麒麟系统 inotify 不可用时的兼容性问题。
"""

from __future__ import annotations

import threading
import time
import unicodedata
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING, Any

from rich.console import Console

from .hot_rule import RuleCorrector
from .hot_phoneme import PhonemeCorrector

# 尝试导入主项目的统一组件，失败则使用本地默认值（独立运行模式）
try:
    from config_client import ClientConfig
    HOT_THRESH = ClientConfig.hot_thresh
    HOT_SIMILAR = ClientConfig.hot_similar
except ImportError:
    HOT_THRESH = 0.8
    HOT_SIMILAR = 0.6

try:
    from cw_linux.logger import get_logger
    logger = get_logger('client')
except ImportError:
    import logging
    logger = logging.getLogger('cw_linux.hotword')

try:
    from cw_linux.state import console
except ImportError:
    console = Console(highlight=False)


class HotwordManager:
    """热词管理器：负责资源协调、热词文件加载与动态监控"""

    def __init__(self,
                 hotword_files: Optional[Dict[str, Path]] = None,
                 threshold: float = 0.7,
                 similar_threshold: Optional[float] = None):
        """
        Args:
            hotword_files: 文件映射 {'hot': Path, 'rule': Path}
            threshold: 纠错阈值
            similar_threshold: 相似度阈值
        """
        self.files = hotword_files or {
            'hot': Path('hot.txt'),
            'rule': Path('hot-rule.txt'),
        }

        self.threshold = threshold
        self.similar_threshold = similar_threshold

        self.phoneme_corrector = PhonemeCorrector(
            threshold=threshold,
            similar_threshold=similar_threshold
        )
        self.rule_corrector = RuleCorrector()

        # 轮询监控状态 {路径: mtime}
        self._watcher_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._mtimes: Dict[str, float] = {}

    def _get_display_width(self, text: str) -> int:
        """计算字符串的显示宽度（中文字符占2个单位）"""
        width = 0
        for char in text:
            if unicodedata.east_asian_width(char) in ('W', 'F', 'A'):
                width += 2
            else:
                width += 1
        return width

    def _format_msg(self, label: str, filename: str, count: int) -> str:
        w = self._get_display_width(label)
        padding1 = " " * max(0, 8 - w)
        w2 = self._get_display_width(filename)
        padding2 = " " * max(0, 16 - w2)
        return "[bold cyan]%s%s：[/][cyan]%s%s[/] 已更新[green]%3d[/]条" % (
            label, padding1, filename, padding2, count
        )

    def load_all(self) -> None:
        """初次加载所有资源"""
        logger.info("正在加载热词资源...")
        self._load_hot()
        self._load_rule()
        logger.info("热词资源加载完成")

    def _read_file(self, key: str) -> str:
        path = self.files.get(key)
        if not path:
            return ""
        try:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# 热词文件单行一个\n", encoding='utf-8')
                return ""
            return path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error("读取文件失败 %s: %s" % (path, e))
            return ""

    def _load_hot(self) -> None:
        content = self._read_file('hot')
        num = self.phoneme_corrector.update_hotwords(content)
        console.print(self._format_msg("热词库", "hot.txt", num))

    def _load_rule(self) -> None:
        content = self._read_file('rule')
        num = self.rule_corrector.update_rules(content)
        console.print(self._format_msg("规则库", "hot-rule.txt", num))

    def get_phoneme_corrector(self) -> PhonemeCorrector:
        return self.phoneme_corrector

    def get_rule_corrector(self) -> RuleCorrector:
        return self.rule_corrector

    def start(self) -> None:
        """开启热词服务：加载资源并启动文件监视"""
        self.load_all()
        self.start_file_watcher()

    def stop(self) -> None:
        """关闭热词服务"""
        self.stop_file_watcher()

    def start_file_watcher(self) -> Any:
        """启动文件监视（轮询实现，兼容无 inotify 环境）"""
        if self._watcher_thread and self._watcher_thread.is_alive():
            return self._watcher_thread

        self._stop_event.clear()
        self._snapshot_mtimes()

        self._watcher_thread = threading.Thread(
            target=self._poll_loop,
            name='cw-hotword-watcher',
            daemon=True
        )
        self._watcher_thread.start()
        logger.debug("已启动热词文件轮询监视: %s" % set(str(p.absolute()) for p in self.files.values()))
        return self._watcher_thread

    def stop_file_watcher(self) -> None:
        """停止文件监视"""
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._stop_event.set()
            self._watcher_thread.join(timeout=2)
            self._watcher_thread = None
            logger.debug("热词文件监视已停止")

    def _snapshot_mtimes(self) -> None:
        """记录当前所有热词文件的修改时间"""
        self._mtimes = {}
        for p in self.files.values():
            try:
                ap = str(p.absolute())
                self._mtimes[ap] = p.stat().st_mtime if p.exists() else 0.0
            except OSError:
                self._mtimes[ap] = 0.0

    def _poll_loop(self) -> None:
        """轮询检测文件变化，3 秒防抖后重载"""
        while not self._stop_event.wait(1.0):
            for key, p in self.files.items():
                ap = str(p.absolute())
                try:
                    mtime = p.stat().st_mtime if p.exists() else 0.0
                except OSError:
                    mtime = 0.0

                old = self._mtimes.get(ap)
                if old is not None and mtime != old and mtime != 0.0:
                    self._mtimes[ap] = mtime
                    time.sleep(3)  # 防抖等待编辑器写完
                    try:
                        handler = self._load_hot if key == 'hot' else self._load_rule
                        handler()
                        logger.info("热词文件已自动重新加载: %s" % p.name)
                    except Exception as e:
                        logger.error("更新热词失败: %s" % e, exc_info=True)
                    break  # 一轮只处理一个变化，防止重复加载
                elif old is None or mtime == 0.0:
                    self._mtimes[ap] = mtime
