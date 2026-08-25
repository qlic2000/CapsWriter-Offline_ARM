#!/usr/bin/env bash
#
# 在【有互联网】的机器上下载全部离线依赖包 (wheels + 源码包)
#
# 用法：
#   ./build_wheels.sh                       # 默认按本机平台+Python版本下载（推荐在 aarch64 麒麟机上直接跑）
#   ./build_wheels.sh cp38-manylinux_aarch64 # 指定目标标签组合（见下方说明）
#
# 说明：
#   - 若下载机就是麒麟 V10 arm64（python3 --version 为 3.7.x），
#     直接运行即可，产物位于 wheels/ 目录。
#   - 若下载机是 x86_64 Linux，可通过 pip 的 --platform/--python-version 参数
#     交叉下载 aarch64 轮子（脚本已内置支持）。
#
set -e

TARGET="${1:-auto}"
OUT_DIR="wheels"
mkdir -p "$OUT_DIR"

if [ "$TARGET" = "auto" ]; then
    echo "[*] 按当前机器环境下载 wheels -> $OUT_DIR/"
    python3 -m pip download \
        -r requirements.txt \
        -d "$OUT_DIR" \
        --only-binary=:all: || {
        echo "[!] 存在无二进制轮子的包，尝试允许源码分发包..."
        python3 -m pip download -r requirements.txt -d "$OUT_DIR"
    }
else
    # TARGET 形如: cp38-manylinux_aarch64
    PYVER="${TARGET%%-*}"          # cp38
    PLAT="${TARGET#*-}"            # manylinux_aarch64
    PYPY="${PYVER/cp/3.}"          # 3.8
    case "$PYPY" in
        3.7) PYPY="3.7";;
        3.8) PYPY="3.8";;
        3.9) PYPY="3.9";;
        3.10) PYPY="3.10";;
    esac

    echo "[*] 交叉下载: python=$PYPY platform=$PLAT -> $OUT_DIR/"
    for pkg in websockets sounddevice pynput pypinyin rapidfuzz rich colorama; do
        python3 -m pip download "$pkg" -d "$OUT_DIR" \
            --only-binary=:all: \
            --platform "$PLAT" \
            --implementation cp \
            --python-version "$PYPY" \
            --abi "${PYVER}" \
        || python3 -m pip download "$pkg" -d "$OUT_DIR" \
            --only-binary=:all: \
            --platform any \
            --python-version "$PYPY"
    done
fi

echo ""
echo "[✓] 完成。请将整个 linux-client 目录打包带走："
echo "    tar czf cw-linux-client.tar.gz ../linux-client/"
echo ""
echo "wheels 清单:"
ls -lh "$OUT_DIR"
