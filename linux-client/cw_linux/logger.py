# coding: utf-8
"""
日志模块（自 core/logger.py 精简移植）

文件日志按配置级别记录，控制台仅输出 WARNING 及以上，
正常业务输出由 rich console 在各模块中直接打印。
"""

import os
import logging
from logging.handlers import RotatingFileHandler

try:
    from rich.logging import RichHandler
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


class TruncatingFileHandler(RotatingFileHandler):
    """超过 maxBytes 后清空文件重写，仅保留末尾几行"""

    _TAIL_LINES = 10

    def doRollover(self):
        tail = ''
        try:
            with open(self.baseFilename, 'r', encoding=self.encoding) as f:
                lines = f.readlines()
                tail = ''.join(lines[-self._TAIL_LINES:]).rstrip()
        except Exception:
            pass

        if self.stream:
            self.stream.close()
            self.stream = None
        self.stream = open(self.baseFilename, 'w', encoding=self.encoding)
        self.stream.write('--- Log truncated at %s\n' % self._now())
        if tail:
            self.stream.write('--- Last %d lines of previous entries:\n%s\n\n' % (self._TAIL_LINES, tail))
        self.stream.flush()


class Logger:
    """日志系统管理器（单例缓存）"""

    _loggers = {}

    @classmethod
    def setup(cls, name, log_dir=None, level='INFO', max_bytes=10 * 1024 * 1024):
        """
        初始化日志记录器

        Args:
            name: 日志名（'client'）
            log_dir: 日志目录，默认 项目根/logs
            level: 文件日志级别
            max_bytes: 单文件最大字节数
        """
        file_level = getattr(logging, str(level).upper(), logging.INFO)
        console_level = logging.WARNING

        if name in cls._loggers:
            logger = cls._loggers[name]
            logger.setLevel(min(file_level, console_level))
            for handler in logger.handlers:
                if isinstance(handler, RotatingFileHandler):
                    handler.setLevel(file_level)
                else:
                    handler.setLevel(console_level)
            return logger

        logger = logging.getLogger(name or None)
        logger.setLevel(min(file_level, console_level))
        if name:
            logger.propagate = False

        if log_dir is None:
            try:
                from config_client import BASE_DIR
                log_dir = os.path.join(BASE_DIR, 'logs')
            except ImportError:
                log_dir = os.path.join(os.getcwd(), 'logs')

        if not os.path.isabs(log_dir):
            log_dir = os.path.abspath(log_dir)

        try:
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, '%s_latest.log' % (name or 'root'))
            formatter = logging.Formatter(
                fmt='%(asctime)s.%(msecs)03d %(levelname)-5s [%(filename)20s:%(lineno)-3d] %(message)s',
                datefmt='%H:%M:%S'
            )
            file_handler = TruncatingFileHandler(log_file, maxBytes=max_bytes, encoding='utf-8')
            file_handler.setLevel(file_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            # 只读文件系统等极端情况下退化为纯控制台日志
            print('[logger] 无法创建日志文件: %s' % e)

        if _HAS_RICH:
            stream_handler = RichHandler(
                level=console_level,
                rich_tracebacks=True,
                markup=True,
                show_path=False
            )
        else:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(console_level)
        logger.addHandler(stream_handler)

        cls._loggers[name] = logger
        return logger

    @classmethod
    def get_logger(cls, name):
        """获取已初始化的记录器，未初始化则按 INFO 创建"""
        if name not in cls._loggers:
            return cls.setup(name, level='INFO')
        return cls._loggers[name]


def setup_logger(name, log_dir=None, level='INFO', **kwargs):
    return Logger.setup(name, log_dir, level, **kwargs)


def get_logger(name):
    return Logger.get_logger(name)
