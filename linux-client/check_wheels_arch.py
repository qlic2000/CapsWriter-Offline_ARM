# coding: utf-8
"""校验 wheels 目录中所有 .so 文件的目标架构是否为 aarch64"""
import zipfile
import glob
import struct
import sys

ok = True
found_any = False

wheels_dir = sys.argv[1] if len(sys.argv) > 1 else "."

for whl in sorted(glob.glob(wheels_dir + "/*.whl")):
    if "manylinux" not in whl:
        continue
    with zipfile.ZipFile(whl) as z:
        for n in z.namelist():
            if not n.endswith(".so"):
                continue
            found_any = True
            data = z.read(n)
            if data[:4] != b"\x7fELF":
                print("%s: %s 不是 ELF" % (whl, n))
                ok = False
                continue
            # ELF64: e_machine 位于偏移 18-19 (little-endian)
            e_machine = struct.unpack("<H", data[18:20])[0]
            EM_AARCH64 = 0xB7
            name = n.split("/")[-1]
            if e_machine == EM_AARCH64:
                print("%s: %s -> aarch64 OK" % (whl.split("/")[-1], name))
            else:
                print("%s: %s -> e_machine=%#x 不是 aarch64!" % (whl, name, e_machine))
                ok = False

if not found_any:
    print("未找到含 .so 的二进制包")
print(">>> 校验通过：全部 .so 均为 aarch64 <<<" if ok and found_any else ">>> 校验失败 <<<")
