#!/usr/bin/env bash
#
# 在【有互联网的 Linux 机器】上下载全部离线依赖包 (wheels)
#
# 用法：
#   ./build_wheels.sh                # 按本机平台+Python版本下载（推荐在 arm64 麒麟机上跑）
#   ./build_wheels.sh 3.7            # 交叉下载：指定目标机 Python 版本（默认 manylinux2014_aarch64）
#   ./build_wheels.sh 3.8 manylinux_2_17_aarch64   # 自定义平台标签
#
# Windows 用户请改用 download_wheels_windows.bat / .ps1，功能相同。
#
set -e

PYVER_TARGET="${1:-auto}"
PLAT="${2:-manylinux2014_aarch64}"
OUT_DIR="wheels"
mkdir -p "$OUT_DIR"

if [ "$PYVER_TARGET" = "auto" ]; then
    echo "[*] 按当前机器环境下载 wheels -> $OUT_DIR/"
    python3 -m pip download \
        -r requirements.txt \
        -d "$OUT_DIR" \
        --only-binary=:all: || {
        echo "[!] 存在无二进制轮子的包，尝试允许源码分发包..."
        python3 -m pip download -r requirements.txt -d "$OUT_DIR"
    }
else
    # 交叉下载模式：在任意架构 Linux 上为目标机下载 aarch64 包
    echo "[*] 交叉下载: python=$PYVER_TARGET platform=$PLAT -> $OUT_DIR/"
    # 直接依赖逐个 --no-deps 下载（pynput 的 evdev 条件依赖无 aarch64 轮子，
    # 由目标机系统包 python3-evdev 提供；整树解析会 ResolutionImpossible）
    for pkg in "websockets>=10.4,<16" "sounddevice>=0.4.6" "pynput>=1.7.6" \
               "pypinyin>=0.44" "rapidfuzz>=2.0,<3.13" "rich>=12.0" "colorama>=0.4.4" "cffi>=1.15"; do
        python3 -m pip download "$pkg" -d "$OUT_DIR" \
            --no-deps \
            --only-binary=:all: \
            --platform "$PLAT" \
            --implementation cp \
            --python-version "$PYVER_TARGET" || echo "[!] 失败: $pkg"
    done

    # 传递依赖显式补充
    for pkg in six python-xlib markdown-it-py mdurl pygments pycparser; do
        python3 -m pip download "$pkg" -d "$OUT_DIR" \
            --only-binary=:all: \
            --platform "$PLAT" \
            --implementation cp \
            --python-version "$PYVER_TARGET" \
            --no-deps || echo "[!] 跳过: $pkg"
    done
fi

echo ""
echo "[✓] 完成。wheels 清单:"
ls -lh "$OUT_DIR"
echo ""
echo "请将整个 linux-client 目录打包带走："
echo "    tar czf cw-linux-client.tar.gz ../linux-client/"
