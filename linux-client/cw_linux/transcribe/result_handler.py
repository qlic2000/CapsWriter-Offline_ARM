# coding: utf-8
"""
转录结果保存器（精简自 core/client/transcribe/result_handler.py）

生成 .txt（按标点切分）、.json（时间戳）与 .srt 字幕，
不依赖第三方 srt/typer 库。
"""

import re
import json
from pathlib import Path
from typing import Dict, List

from config_client import ClientConfig as Config
from cw_linux.protocol import RecognitionMessage
from cw_linux.logger import get_logger

logger = get_logger('client')


def _format_srt_time(seconds: float) -> str:
    """将秒数格式化为 SRT 时间格式 00:00:00,000"""
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


class ResultHandler:
    """转录结果处理器：文本切分与文件保存"""

    @staticmethod
    def smart_split(text: str, min_chars: int = 2) -> str:
        """
        智能分行：保留标点，避免在逗号处切分过短的句子，
        英文标点需后跟空白才切分（避免 3.14 被切开）。
        """
        parts = re.split(r'([，。？]|[.,?!](?:\s+|$))', text)
        lines = []
        buffer = ""

        strong_punct = {'。', '？', '.', '?', '!'}
        punct_chars = set(r'，。？,.?!')

        for part in parts:
            clean_part = part.strip()
            if clean_part and clean_part in punct_chars and len(clean_part) == 1:
                buffer += part
                is_strong = clean_part in strong_punct
                if is_strong or len(buffer) > min_chars:
                    lines.append(buffer)
                    buffer = ""
            else:
                buffer += part

        if buffer:
            lines.append(buffer)

        return "\n".join(lines)

    @classmethod
    def save_results(cls, file: Path, message: RecognitionMessage) -> str:
        """
        保存转录结果文件

        Returns:
            text_display: 原始拼接文本（用于控制台显示）
        """
        text_display = message.text
        text_accu = message.text_accu if message.text_accu else message.text
        text_split = cls.smart_split(text_accu)
        timestamps = message.timestamps
        tokens = message.tokens

        json_filename = file.with_suffix('.json')
        txt_filename = file.with_suffix('.txt')
        srt_filename = file.with_suffix('.srt')

        # 1. txt
        if Config.file_save_txt:
            with open(txt_filename, 'w', encoding='utf-8') as f:
                f.write(text_split)
            logger.debug("保存切分文本: %s" % txt_filename)

        # 2. json
        if Config.file_save_json:
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump({'timestamps': timestamps, 'tokens': tokens}, f, ensure_ascii=False)
            logger.debug("保存 JSON 结果: %s" % json_filename)

        # 3. srt：字级时间戳与分行文本对齐后按行生成字幕
        if Config.file_save_srt and timestamps and tokens:
            try:
                cls._save_srt(srt_filename, text_split.splitlines(), tokens, timestamps)
            except Exception as e:
                logger.warning("生成 SRT 失败: %s" % e)

        return text_display

    @classmethod
    def _save_srt(cls, srt_filename: Path, text_lines: List[str],
                  tokens: List[str], timestamps: List[float]) -> None:
        """
        按分行文本对齐 token 时间戳生成 SRT。

        策略：将 tokens 展开为字符序列并携带时间戳，
        再顺序消费每个字幕行的字符数进行切分。
        """
        chars = []  # [(char, start_ts)]
        for token, ts in zip(tokens, timestamps):
            for ch in str(token):
                chars.append((ch, ts))

        subtitles = []
        idx = 0
        line_no = 1
        total = len(chars)

        for line in text_lines:
            line_clean = line.strip()
            n = len(line_clean.replace(' ', ''))
            if n == 0:
                continue
            start_idx = idx
            end_idx = min(idx + n, total)

            if start_idx >= total:
                break

            start_ts = chars[start_idx][1]
            end_ts = chars[end_idx - 1][1] + 0.35  # 行尾留一点显示时长
            if end_idx < total:
                end_ts = min(end_ts, chars[end_idx][1])

            subtitles.append((start_ts, end_ts, line_clean))
            idx = end_idx
            line_no += 1

        # 尾部剩余字符并入最后一行
        if idx < total and subtitles:
            last_start, _, last_text = subtitles[-1]
            subtitles[-1] = (last_start, chars[total - 1][1] + 0.35, last_text)

        with open(srt_filename, 'w', encoding='utf-8') as f:
            for i, (start_ts, end_ts, text) in enumerate(subtitles, start=1):
                f.write("%d\n" % i)
                f.write("%s --> %s\n" % (_format_srt_time(start_ts), _format_srt_time(end_ts)))
                f.write("%s\n\n" % text)

        logger.debug("保存 SRT 字幕: %s (%d 条)" % (srt_filename, len(subtitles)))
