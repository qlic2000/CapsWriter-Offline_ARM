# CapsWriter Offline — Linux 客户端（银河麒麟 V10 / arm64）

本客户端基于 [CapsWriter-Offline](../readme.md) 的 Windows 服务端 + Windows 客户端架构移植，
面向 **无互联网的局域网环境** 部署：

- **Windows 服务器**：继续使用原有 Windows 服务端，负责 AI 模型推理（无需任何改动）。
- **麒麟 V10 arm64 终端**：运行本项目 Linux 客户端，通过局域网 WebSocket 连接服务端，
  实现「按住快捷键说话、松开上屏」的语音输入，以及音视频文件转录字幕。

## 功能对照

| 功能 | Windows 客户端 | Linux 客户端 | 说明 |
|------|:---:|:---:|------|
| 按住说话实时上屏 | ✅ | ✅ | 默认 CapsLock 长按；X11 下可阻塞按键 |
| 热词音素替换 (hot.txt) | ✅ | ✅ | 与 Windows 版同一套 RAG 音素算法 |
| 正则规则替换 (hot-rule.txt) | ✅ | ✅ | 文件格式完全一致 |
| 文件拖入转录 (srt/txt/json) | ✅ | ✅ | 命令行传参方式 `python3 start_client.py 文件` |
| 录音保存 + 日记归档 | ✅ | ✅ | 年/月/assets/ 结构一致 |
| 繁体转换 / 末尾标点消除 | ✅ | ✅ | |
| LLM 角色润色 | ✅ | ❌ 精简 | 局域网场景通常无 LLM API |
| 系统托盘 / Toast 弹窗 | ✅ | ❌ 精简 | 终端 rich 输出代替 |
| UDP 广播/控制、鼠标侧键 | ✅ | ❌ 精简 | |

## 目录结构

```
linux-client/
├── start_client.py        # 启动入口
├── config_client.py       # 全部配置（服务端地址、快捷键等）
├── hot.txt                # 热词文件（与 Windows 版通用）
├── hot-rule.txt           # 正则替换规则（与 Windows 版通用）
├── requirements.txt       # Python 依赖清单
├── build_wheels.sh        # 【联网机器】下载离线依赖包
├── install_offline.sh     # 【目标机】离线安装脚本
├── run_client.sh          # 日常启动脚本
├── cw_linux/              # 客户端源码包
│   ├── app.py             # 门面类 CapsWriterClient
│   ├── protocol.py        # 与 Windows 服务端共享的通信协议
│   ├── websocket_manager.py   # WebSocket 连接管理
│   ├── audio/             # 录音流(PulseAudio/ALSA)、录音器、录音文件
│   ├── hotkey/            # Linux 全局快捷键 (pynput/X11) + 终端回退
│   ├── hotword/           # 热词音素 RAG 系统（自 Windows 版整体移植）
│   ├── output/            # 结果后处理、文本输出(xdotool/wtype)、剪贴板(xclip)
│   └── transcribe/        # 文件转录 (FFmpeg + srt/txt/json)
└── wheels/                # build_wheels.sh 生成的离线依赖包（打包时带上）
```

## 离线部署步骤

### 第一步：在 Windows 联网机上下载 arm64 依赖包

> 无需任何 arm64 设备。`pip download` 支持 `--platform/--python-version`
> 交叉参数，在 x86_64 Windows 上即可解析并下载 aarch64 Linux 的 wheel 包。
> （本方案的交叉下载命令已在 Linux 沙箱按相同参数逐包实测通过）

```text
1. Windows 电脑需装有 Python 3.7+（安装时勾选 Add to PATH）
   下载地址: https://www.python.org/downloads/windows/

2. 把整个 linux-client 目录拷贝到 Windows 电脑

3. 双击 linux-client\download_wheels_windows.bat
  （或右键 download_wheels_windows.ps1 -> 使用 PowerShell 运行）
   如下载不了，可PowerShell临时设置系统 pip 默认清华源，再运行脚本：
   python -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
   python -m pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

4. 等待完成，wheels\ 目录会生成约 16 个 .whl 文件（aarch64 / cp37）
```

脚本默认按目标机 **Python 3.7**（麒麟 V10 自带）下载。若目标机装了
其他版本，用参数指定，例如 PowerShell 中执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\download_wheels_windows.ps1 -PyVer 3.8
```

同时请在联网环境准备好麒麟系统的 RPM 包（目标机可能缺失），
可从 [麒麟软件商店](https://software.kylinos.cn) 或 openKylin/麒麟官方源下载：
     https://archive.kylinos.cn/kylin/KYLIN-ALL/
```
portaudio-devel  ffmpeg  xclip  xdotool  pulseaudio  python3-evdev
```

### 第二步：拷贝到目标机并打包

将 `linux-client` 整个目录（含 `wheels\`）压缩后通过 U 盘 / 内网文件服务器带到银河麒麟机器：

- Windows 上：右键文件夹 → 发送到 → 压缩(zipped)文件夹
- 或 PowerShell: `Compress-Archive -Path linux-client -DestinationPath cw-linux-client.zip`

### 第三步：在银河麒麟 V10 目标机上解压并安装

```bash
tar xzf cw-linux-client.tar.gz
cd linux-client
chmod +x install_offline.sh
./install_offline.sh
```

脚本会自动完成：
1. 检查 python3 ≥ 3.7；
2. 检查系统级依赖并给出缺失项的 yum 安装提示；
3. 创建 `.venv` 虚拟环境，从本地 `wheels/` 离线安装全部 Python 依赖（全程不访问互联网）。

系统级依赖（缺失时按需安装）：

```bash
sudo yum install -y portaudio-devel ffmpeg xclip xdotool pulseaudio
```

- `portaudio-devel`：**录音必需**
- `ffmpeg`：录音存 MP3、文件转录必需（不装则录音退化为 WAV、无法转录）
- `xclip`：剪贴板必需
- `xdotool`：识别结果模拟键入上屏必需（X11 会话）
- `pulseaudio`：推荐音频后端

### 第三步：配置服务端地址并运行

编辑 `config_client.py`：

```python
class ClientConfig:
    addr = '192.168.1.100'   # ← 改为局域网内 Windows 服务端 IP
    port = '6016'
```

启动：

```bash
./run_client.sh            # 或 source .venv/bin/activate && python3 start_client.py
```

看到「已连接服务端」后，在任意应用中**按住 CapsLock 说话、松开即上屏**。

## 使用方式

### 实时语音听写
- 按住 `CapsLock` 开始说话，松开后识别结果自动输入到当前焦点窗口。
- 按压时间 < 0.3 秒视为误触，自动取消并补发原按键（不影响大小写切换）。

### 文件转录

```bash
python3 start_client.py 会议录音.mp4 视频.avi
```

会在源文件旁生成同名 `.srt` 字幕、`.txt` 文本、`.json` 时间戳。

### 热词维护
- 编辑 `hot.txt`（单行一个热词，支持 `|` 别名、`~~~` 黑名单），保存后约 4 秒自动重载。
- 编辑 `hot-rule.txt`（`pattern = replacement` 正则规则），同样自动重载。

## 配置速查（config_client.py）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `addr` / `port` | 127.0.0.1 / 6016 | Windows 服务端地址端口 |
| `shortcuts` | caps_lock | 快捷键列表，支持 keyboard / terminal 两类 |
| `suppress` | True | X11 下阻塞原按键；Wayland 请改 False |
| `paste` | False | 输出方式：模拟打字 / 剪贴板粘贴 |
| `save_audio` | True | 本地保存录音 |
| `linux.audio_api` | auto | 强制音频后端：auto/pulse/alsa |
| `linux.type_tool` | auto | 上屏工具：auto/xdotool/wtype |
| `trash_punc_thresh` | 8 | 短句自动去末尾标点的阈值 |

## 故障排查

所有日志集中在 `logs/client_latest.log`。

| 现象 | 处理方法 |
|------|----------|
| 反复提示「连接服务端被拒绝」 | 确认 Windows 端 `start_server.exe` 已启动；确认防火墙放行 6016 端口；`telnet 服务端IP 6016` 测试连通性 |
| 无法初始化音频 / PortAudio 报错 | `sudo yum install portaudio-devel`；将用户加入 audio 组：`sudo usermod -aG audio $USER` 后重新登录 |
| 无声或设备选择错误 | 尝试 `linux.audio_api='alsa'`，或用 `python3 -m sounddevice` 查看可用设备后指定 `linux.input_device` |
| 识别结果没有上屏 | 安装 `xdotool`（X11）或 `wtype`（Wayland）；工具缺失时会自动把结果复制到剪贴板兜底 |
| Wayland 下按键无法阻塞 / CapsLock 状态错乱 | 将对应快捷键的 `suppress` 改为 `False`，或换用 f9 等不敏感按键 |
| SSH/无图形环境使用 | 在 `shortcuts` 中加入 `{'key':'enter','type':'terminal','hold_mode':False,'enabled':True}`，终端回车开始说话 |
| pynput 启动失败 | X11 需要 `DISPLAY` 变量；root 权限程序需以 root 运行客户端 |
| 热词不生效 | 查看 `logs/client_latest.log` 是否有加载报错；确认修改保存后等待 4 秒防抖窗口 |

## FAQ

**Q: 为什么在 Windows 上就能下载 Linux arm64 的包？原理是什么？**  
A: `pip download` 的 `--platform manylinux2014_aarch64 --python-version 3.7`
参数让 pip 不按本机环境、而按指定目标平台去解析和下载 wheel。
wheel 本质是 zip 包，文件名中的平台标签决定了兼容性——下载动作本身
与平台无关，只要 PyPI 上存在 `manylinux2014_aarch64` 轮子即可拿到。

**Q: 下载时报 rapidfuzz 找不到匹配版本？**  
A: 这是交叉下载最常见的坑：rapidfuzz 等包的 aarch64 轮子只带
`cp37-cp37m` ABI 标签（不带 abi3），若 pip 命令加了 `--abi cp37`
以外的限制或版本过新都会匹配失败。本仓库脚本已内置正确参数
（省略 --abi、锁定 `<3.13`），直接使用脚本即可。

**Q: 目标机安装时提示 No matching distribution found for evdev？**  
A: pynput 在 Linux 上依赖 evdev，但 PyPI 没有 evdev 的 aarch64 预编译
轮子。解决方法：目标机用系统 RPM 安装 `sudo yum install python3-evdev`，
venv 已配置 `--system-site-packages` 可直接引用它（install_offline.sh 已内置该检查）。

**Q: wheels 里混入了 x86_64 或 win_amd64 的包怎么办？**  
A: 正常不会出现——脚本所有命令都带 `--platform` 与 `--only-binary`。
若手工补包，务必带上相同参数；可用 `pip download <pkg> --platform manylinux2014_aarch64 ...`
重新下载覆盖。

**Q: 麒麟 V10 自带 Python 3.7，依赖版本兼容吗？**  
A: 兼容。requirements.txt 中各依赖均保留了支持 Python 3.7 的版本线
（websockets 10.x~15.x、rapidfuzz 3.x、rich 13.x 等）。若 pip 解析到过新版本导致安装失败，
可在 requirements.txt 中手动加上限，如 `websockets>=10.4,<13`。

**Q: 与 Windows 客户端可以同时连一个服务端吗？**  
A: 可以。服务端为每个 WebSocket 连接独立建立会话，多客户端并发互不影响。

**Q: 为什么精简了 LLM 角色、托盘等功能？**  
A: LLM 角色依赖外部大模型 API，离线局域网通常不可用；托盘/Toast 属于桌面深度集成，
跨发行版兼容成本高。核心的「语音转文字 + 热词 + 文件转录」链路完整保留。

## 验证情况（开发沙箱）

以下验证已在 x86_64 Linux 沙箱完成，逻辑与 arm64 一致（仅二进制依赖需 arm64 轮子）：

- [x] 全部模块语法检查通过
- [x] 依赖解析与 venv 离线安装流程
- [x] 协议序列化与 Windows 版字段级兼容（AudioMessage/RecognitionMessage）
- [x] 热词系统：21 条热词加载，「克劳德→Claude」「酷的→CUDA」音素替换正确
- [x] 规则替换：「四千毫安时→四千mAh」生效
- [x] 模拟服务端端到端联调：WAV → FFmpeg 提取 → 流式发送 → 收取结果 → srt/txt/json 三件套生成
- [x] 无图形/无剪贴板/无 PortAudio 环境的安全降级
