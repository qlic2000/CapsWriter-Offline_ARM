#!/usr/bin/env bash
# CapsWriter Linux 客户端启动脚本
set -e
cd "$(dirname "$0")"

# 激活虚拟环境（若存在）
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

exec python3 start_client.py "$@"
