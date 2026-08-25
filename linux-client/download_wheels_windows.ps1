# ============================================================
#  CapsWriter Offline Linux 客户端 —— Windows 联网机交叉下载脚本
#
#  用途：在【有互联网的 Windows x86_64 电脑】上，为 arm64 银河麒麟
#        V10 目标机下载全部离线 Python 依赖（wheel 包）。
#
#  用法：
#    方式一（推荐，自动找 python）：双击 download_wheels_windows.bat
#    方式二：powershell -ExecutionPolicy Bypass -File .\download_wheels_windows.ps1 [-PyVer 3.7]
#
#  参数 -PyVer：目标机的 Python 版本，默认 3.7（麒麟 V10 自带）。
#  若目标机装了其他版本（如 3.8/3.10），请对应修改。
#
#  原理：
#    pip download 支持 --platform/--python-version 交叉参数，
#    在 x86_64 Windows 上即可解析并下载 aarch64 Linux 的 wheel，
#    无需任何 arm64 设备。含 C 扩展的包会自动匹配 manylinux2014_aarch64 轮子。
# ============================================================

param(
    [string]$PyVer = "3.7",          # 目标机 Python 版本
    [string]$OutDir = "wheels"       # 产物目录
)

$ErrorActionPreference = "Stop"

# ---- 定位本机 python ----
$Python = $null
foreach ($cmd in @("python", "py")) {
    try {
        $v = & $cmd --version 2>$null
        if ($LASTEXITCODE -eq 0) { $Python = $cmd; break }
    } catch { }
}
if (-not $Python) {
    Write-Host "[X] 未找到 python。请先安装 Python 3.7+ 并勾选 'Add to PATH'。" -ForegroundColor Red
    Write-Host "    下载地址: https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    exit 1
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " CapsWriter Offline Linux 客户端 离线包下载"
Write-Host " 本机:   $(& $Python --version) (仅作 pip 运行环境)"
Write-Host " 目标:   银河麒麟 V10 arm64, Python $PyVer"
Write-Host " 产物:   $((Resolve-Path .).Path)\$OutDir"
Write-Host "==============================================" -ForegroundColor Cyan

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

# 平台标签：manylinux2014 兼容麒麟 V10 的 glibc(2.28)
$Platform = "manylinux2014_aarch64"

# 直接依赖清单（与 requirements.txt 一致）
# 注意：evdev 是 pynput 在 Linux 上的依赖但 PyPI 无 aarch64 预编译轮子，
#       改由目标机 yum 安装系统 RPM 包 python3-evdev 提供见 install_offline.sh
$Pkgs = @(
    "websockets>=10.4,<16",
    "sounddevice>=0.4.6",
    "pynput>=1.7.6",
    "pypinyin>=0.44",
    "rapidfuzz>=2.0,<3.13",
    "rich>=12.0",
    "colorama>=0.4.4"
)
# 传递依赖显式列出（交叉模式下 pip 无法完整回溯部分平台条件依赖）
$Transitive = @("six", "python-xlib", "markdown-it-py", "mdurl", "pygments", "pycparser")

$failed = @()

Write-Host "`n[*] 第一步：逐个下载直接依赖（--no-deps，依赖关系由下方显式清单保证）..." -ForegroundColor Green
# 重要：必须 --no-deps 逐包下载。若让 pip 自动解析整个依赖树，
# pynput 的 Linux 条件依赖 evdev（PyPI 无 aarch64 预编译轮子，由目标机
# 系统 RPM 包 python3-evdev 提供）会导致 ResolutionImpossible。
foreach ($pkg in $Pkgs) {
    Write-Host ("  -> {0}" -f $pkg)
    # 注意：不传 --abi 参数。指定 cp37 等 ABI 标签会导致 rapidfuzz 这类
    # 只发 cpXY 标签轮子的包匹配失败；省略后 pip 自动接受全部兼容 ABI。
    & $Python -m pip download $pkg `
        --no-deps `
        --only-binary=:all: `
        --platform $Platform `
        --implementation cp `
        --python-version $PyVer `
        -d $OutDir --no-cache-dir
    if ($LASTEXITCODE -ne 0) { $failed += $pkg }
}

Write-Host "`n[*] 第二步：下载传递依赖 ..." -ForegroundColor Green
foreach ($pkg in $Transitive) {
    Write-Host ("  -> {0}" -f $pkg)
    & $Python -m pip download $pkg `
        --only-binary=:all: `
        --platform $Platform `
        --implementation cp `
        --python-version $PyVer `
        -d $OutDir --no-deps --no-cache-dir | Out-Null
    if ($LASTEXITCODE -ne 0) { $failed += $pkg }
}

Write-Host "`n[*] 第三步：下载 cffi（sounddevice 底层，aarch64 需要）..." -ForegroundColor Green
& $Python -m pip download "cffi>=1.15" `
    --only-binary=:all: `
    --platform $Platform `
    --implementation cp `
    --python-version $PyVer `
    -d $OutDir --no-cache-dir
if ($LASTEXITCODE -ne 0) { $failed += "cffi" }

# 汇总
$wheels = Get-ChildItem $OutDir -Filter *.whl
Write-Host "`n==============================================" -ForegroundColor Cyan
if ($wheels.Count -ge 14 -and $failed.Count -eq 0) {
    Write-Host "[OK] 全部下载完成！共 $($wheels.Count) 个 wheel 包：" -ForegroundColor Green
} else {
    Write-Host "[!] 完成，但有失败项: $($failed -join ', ')" -ForegroundColor Yellow
    Write-Host "    请检查上方报错信息重试对应包。" -ForegroundColor Yellow
}
$wheels | ForEach-Object { Write-Host ("    {0}  ({1:N0} KB)" -f $_.Name, ($_.Length/1KB)) }

$totalMB = [math]::Round(($wheels | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "`n总大小: $totalMB MB" -ForegroundColor Gray
Write-Host ""
Write-Host "[下一步] 将整个 linux-client 目录打包带走：" -ForegroundColor White
Write-Host "    右键 linux-client 文件夹 -> 发送到 -> 压缩(zipped)文件夹"
Write-Host "    或: Compress-Archive -Path ..\linux-client -DestinationPath cw-linux-client.zip"
Write-Host ""
Write-Host "[提示] 目标机还需要以下系统 RPM 包（yum 离线安装）：" -ForegroundColor White
Write-Host "    portaudio-devel ffmpeg xclip xdotool pulseaudio python3-evdev"
