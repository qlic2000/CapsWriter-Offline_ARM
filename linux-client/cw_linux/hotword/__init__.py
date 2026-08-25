# coding: utf-8
try:
    from cw_linux.logger import get_logger
    logger = get_logger('client')
except ImportError:  # pragma: no cover - 独立运行模式
    import logging
    logger = logging.getLogger("cw_linux.hotword")

from .hot_phoneme import PhonemeCorrector, CorrectionResult
from .hot_rule import RuleCorrector
from .manager import HotwordManager

__all__ = [
    'PhonemeCorrector',
    'CorrectionResult',
    'RuleCorrector',
    'HotwordManager',
]
