#!/usr/bin/env python3
# coding: utf-8
"""
CapsWriter Offline Linux 客户端启动入口

用法：
    python3 start_client.py              # 麦克风实时听写模式
    python3 start_client.py 文件1 文件2   # 音视频文件转录模式（生成 srt/txt/json）
"""

import sys
from pathlib import Path

# 确保程序根目录在模块搜索路径中
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from cw_linux.app import CapsWriterClient

if __name__ == "__main__":
    CapsWriterClient().start()
