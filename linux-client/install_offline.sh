#!/usr/bin/env bash
#
# 银河麒麟 V10 (arm64) 离线安装脚本 —— 在【无互联网】的目标机上执行
#
# 功能：
#   1. 检查 python3 版本（>= 3.7）
#   2. 检查/提示系统级依赖：ffmpeg、xclip、xdotool、portaudio、pulseaudio
#   3. 创建隔离 venv 并从 wheels/ 目录离线安装全部 Python 依赖
#   4. 输出后续使用说明
#
set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
WHEELS_DIR="$BASE_DIR/wheels"
VENV_DIR="$BASE_DIR/.venv"

echo "=============================================="
echo " CapsWriter Offline Linux 客户端 离线安装"
echo " 目标目录: $BASE_DIR"
echo "=============================================="

# ---------- 1. Python ----------
if ! command -v python3 >/dev/null; then
    echo "[✗] 未找到 python3，请先安装: sudo yum install python3"
    exit 1
fi

PYVER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PYSUM=$(python3 -c 'import sys; print("%d%02d" % sys.version_info[:2])')
echo "[✓] python3 = $PYVER"

if [ "$PYSUM" -lt 307 ]; then
    echo "[✗] 需要 Python >= 3.7，当前 $PYVER"
    exit 1
fi
if [ "$PYSUM" -ge 300 ] && [ "$PYVER" = "3.7" ]; then
    echo "[i] 检测到 Python 3.7（麒麟 V10 默认），依赖包将按兼容模式安装"
fi

# ---------- 2. 系统依赖检查（仅提示，不强制）----------
check_cmd() {
    if command -v "$1" >/dev/null; then
        echo "  [✓] $1 已安装"
    else
        echo "  [!] 缺少 $1 —— $2"
    fi
}

echo ""
echo "[*] 检查系统级依赖（可通过 yum 离线 rpm 包安装）："
check_cmd ffmpeg   "录音保存 MP3 与 文件转录 必需（不装则退化为 WAV / 无转录）"
check_cmd ffprobe  "文件转录进度显示（可选）"
check_cmd xclip    "剪贴板操作必需（sudo yum install xclip）"
check_cmd xdotool  "识别结果模拟键入上屏必需（X11 会话）"
check_cmd pulseaudio "音频后端 PulseAudio（缺失时自动走 ALSA）"

# portaudio 动态库检查（sounddevice 的底层）
if ldconfig -p 2>/dev/null | grep -q portaudio; then
    echo "  [✓] libportaudio 已安装"
else
    echo "  [!] 缺少 libportaudio2/portaudio-devel —— 录音必需！"
    echo "      麒麟源: sudo yum install portaudio-devel"
fi

if command -v ffmpeg >/dev/null && ! ldconfig -p 2>/dev/null | grep -q portaudio; then
    echo "  [!] 注意：ffmpeg 通常已自带 portaudio，但 sounddevice 仍需系统库"
fi

# 图形会话检测
echo ""
if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    echo "[✓] 检测到图形会话，全局快捷键可用"
else
    echo "[!] 未检测到图形会话 (DISPLAY)，全局快捷键不可用。"
    echo "    请在 config_client.py 的 shortcuts 中加入终端回退快捷键："
    echo "      {'key': 'enter', 'type': 'terminal', 'hold_mode': False, 'enabled': True}"
fi

# ---------- 3. venv + 离线安装 ----------
echo ""
echo "[*] 创建虚拟环境 $VENV_DIR ..."
python3 -m venv "$VENV_DIR"

source "$VENV_DIR/bin/activate"

echo "[*] 从 $WHEELS_DIR 离线安装 Python 依赖..."
pip install --no-index --find-links "$WHEELS_DIR" -r requirements.txt \
    || pip install --no-index --find-links "$WHEELS_DIR" \
        websockets sounddevice pynput pypinyin rapidfuzz rich colorama

deactivate

# ---------- 4. 完成 ----------
cat <<EOF

==============================================
[✓] 安装完成！

日常启动：
    cd $BASE_DIR
    ./run_client.sh

或手动激活环境运行：
    source .venv/bin/activate
    python3 start_client.py

配置服务端地址：
    编辑 config_client.py -> addr = '<Windows 服务端 IP>'

热词与替换规则：
    hot.txt        单行一个热词（音素模糊匹配）
    hot-rule.txt   正则替换规则（pattern = replacement）

日志排查：
    logs/client_latest.log
==============================================
EOF
