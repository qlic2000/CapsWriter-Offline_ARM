# coding: utf-8
"""
通信协议模块（自 core/protocol.py 原样移植）

与 Windows 服务端共享同一套消息格式，保证跨平台互通。
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json


@dataclass
class AudioMessage:
    """
    客户端 -> 服务端：音频数据消息

    Attributes:
        task_id: 任务唯一标识
        source: 音频来源 ('mic' 麦克风 或 'file' 文件)
        data: Base64 编码的音频数据 (float32, 16kHz, mono)
        is_final: 是否为当前任务的最后一个数据包
        time_start: 录音/音频开始时间戳
        seg_duration: 分段时长（秒）
        seg_overlap: 重叠时长（秒）
    """
    task_id: str
    source: str                 # 'mic' 或 'file'
    data: str                   # base64 编码的音频
    is_final: bool
    time_start: float
    seg_duration: float = 15.0
    seg_overlap: float = 2.0
    context: str = ''
    language: str = 'auto'

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> 'AudioMessage':
        return cls(
            task_id=data['task_id'],
            source=data['source'],
            data=data['data'],
            is_final=data['is_final'],
            time_start=data['time_start'],
            seg_duration=data.get('seg_duration', 15.0),
            seg_overlap=data.get('seg_overlap', 2.0),
            context=data.get('context', ''),
            language=data.get('language', 'auto'),
        )


@dataclass
class RecognitionMessage:
    """
    服务端 -> 客户端：识别结果消息

    Attributes:
        task_id: 任务唯一标识
        is_final: 是否为最终结果
        duration: 已处理的音频总时长（秒）
        time_start / time_submit / time_complete: 各阶段时间戳
        text: 主要输出 - 简单文本拼接结果（用于语音输入）
        text_accu: 精确输出 - 基于时间戳去重的拼接结果（用于字幕）
        tokens / timestamps: 字级 token 与时间戳
    """
    task_id: str
    is_final: bool
    duration: float
    time_start: float
    time_submit: float
    time_complete: float

    text: str

    text_accu: str = ''
    tokens: List[str] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'RecognitionMessage':
        return cls(
            task_id=data['task_id'],
            is_final=data['is_final'],
            duration=data['duration'],
            time_start=data['time_start'],
            time_submit=data['time_submit'],
            time_complete=data['time_complete'],
            text=data['text'],
            text_accu=data.get('text_accu', ''),
            tokens=data.get('tokens', []),
            timestamps=data.get('timestamps', []),
        )
