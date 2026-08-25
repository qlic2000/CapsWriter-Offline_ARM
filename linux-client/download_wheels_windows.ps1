# ============================================================
#  CapsWriter Offline Linux Client - Offline Wheel Downloader
#
#  Purpose:
#    On a Windows x86_64 PC WITH internet, download all aarch64
#    Linux wheel packages for the Kylin V10 arm64 target machine.
#    pip download supports --platform/--python-version cross
#    parameters, so NO arm64 device is needed. Binary packages
#    automatically match manylinux2014_aarch64 wheels.
#
#  Usage:
#    Double-click download_wheels_windows.bat  (recommended), or
#    powershell -ExecutionPolicy Bypass -File .\download_wheels_windows.ps1 [-PyVer 3.7]
#
#  Parameter -PyVer: target machine Python version, default 3.7
#  (Kylin V10 system python). Change it if the target uses another
#  version such as 3.8 / 3.10.
#
#  NOTE: Keep this file ASCII-only. It parses correctly under any
#        console code page and any PowerShell version.
# ============================================================
param(
    [string]$PyVer = "3.7",
    [string]$OutDir = "wheels"
)

$ErrorActionPreference = "Stop"

# ---- locate local python launcher ----
$Python = $null
foreach ($cmd in @("python", "py")) {
    try {
        $v = & $cmd --version 2>$null
        if ($LASTEXITCODE -eq 0) { $Python = $cmd; break }
    } catch { }
}
if (-not $Python) {
    Write-Host "[X] Python not found. Install Python 3.7+ and check 'Add to PATH'." -ForegroundColor Red
    Write-Host "    Download: https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    exit 1
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " CapsWriter Offline Linux Client - Wheel Downloader"
Write-Host " Host  : $(& $Python --version) (used to run pip only)"
Write-Host " Target: Kylin V10 arm64, Python $PyVer"
Write-Host " Output: $((Resolve-Path .).Path)\$OutDir"
Write-Host "==============================================" -ForegroundColor Cyan

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

# manylinux2014 is compatible with Kylin V10 glibc (2.28)
$Platform = "manylinux2014_aarch64"

# Direct dependencies (mirrors requirements.txt).
# evdev is NOT here: PyPI has no aarch64 wheel for it; the target
# machine provides it via the system RPM package python3-evdev
# (see install_offline.sh). Downloading with whole-tree resolution
# would fail with ResolutionImpossible, hence per-package --no-deps.
$Pkgs = @(
    "websockets>=10.4,<16",
    "sounddevice>=0.4.6",
    "pynput>=1.7.6",
    "pypinyin>=0.44",
    "rapidfuzz>=2.0,<3.13",
    "rich>=12.0",
    "colorama>=0.4.4"
)
# Transitive dependencies, listed explicitly for cross-download mode.
$Transitive = @("six", "python-xlib", "markdown-it-py", "mdurl", "pygments", "pycparser")
# cffi: underlying library of sounddevice, required on aarch64.
$Extra = @("cffi>=1.15")

$failed = @()

# Common pip arguments. Passed as an array (NOT backtick line
# continuations) so parsing cannot break on any platform.
$downloadArgs = @(
    "--no-deps",
    "--only-binary=:all:",
    "--platform", $Platform,
    "--implementation", "cp",
    "--python-version", $PyVer,
    "-d", $OutDir,
    "--no-cache-dir"
)

function Invoke-PipDownload {
    param([string]$Pkg)
    Write-Host ("  -> {0}" -f $Pkg)
    # No --abi argument on purpose: ABI tags like cp37 make packages
    # that only publish cpXY wheels (e.g. rapidfuzz) fail to match.
    & $Python -m pip download $Pkg @downloadArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { return $false }
    return $true
}

Write-Host ""
Write-Host "[*] Step 1/3: direct dependencies (--no-deps per package)..." -ForegroundColor Green
foreach ($pkg in $Pkgs) {
    if (-not (Invoke-PipDownload -Pkg $pkg)) { $failed += $pkg }
}

Write-Host ""
Write-Host "[*] Step 2/3: transitive dependencies..." -ForegroundColor Green
foreach ($pkg in $Transitive) {
    if (-not (Invoke-PipDownload -Pkg $pkg)) { $failed += $pkg }
}

Write-Host ""
Write-Host "[*] Step 3/3: cffi (required by sounddevice on aarch64)..." -ForegroundColor Green
foreach ($pkg in $Extra) {
    if (-not (Invoke-PipDownload -Pkg $pkg)) { $failed += $pkg }
}

# ---- summary ----
$wheels = Get-ChildItem $OutDir -Filter *.whl
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
if ($wheels.Count -ge 14 -and $failed.Count -eq 0) {
    Write-Host ("[OK] All downloads finished! {0} wheel files:" -f $wheels.Count) -ForegroundColor Green
} else {
    Write-Host ("[!] Finished, but some packages failed: {0}" -f ($failed -join ", ")) -ForegroundColor Yellow
    Write-Host "    Check the errors above and retry those packages." -ForegroundColor Yellow
}
foreach ($w in $wheels) {
    Write-Host ("    {0}  ({1:N0} KB)" -f $w.Name, ($w.Length / 1KB))
}

$totalMB = [math]::Round(($wheels | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host ""
Write-Host ("Total size: {0} MB" -f $totalMB) -ForegroundColor Gray
Write-Host ""
Write-Host "[Next] Copy the whole linux-client folder to the target machine:"
Write-Host "    Right-click linux-client -> Send to -> Compressed (zipped) folder"
Write-Host "    or: Compress-Archive -Path ..\linux-client -DestinationPath cw-linux-client.zip"
Write-Host ""
Write-Host "[Note] The target machine also needs these system RPM packages (yum):"
Write-Host "    portaudio-devel ffmpeg xclip xdotool pulseaudio python3-evdev"
