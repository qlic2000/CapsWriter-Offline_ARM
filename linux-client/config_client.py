# coding: utf-8
"""
Linux 客户端配置文件（银河麒麟 V10 / arm64）

字段含义与 Windows 版 config_client.py 保持一致，另新增 linux 段配置。
"""

import os

# 版本信息
__version__ = '2.6-linux.1'

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class ClientConfig:
    # ======== 服务端连接 ========
    addr = '127.0.0.1'          # Windows 服务端地址（局域网部署时改为服务端 IP）
    port = '6016'               # 服务端端口

    # ======== 快捷键 ========
    # keyboard: 全局键盘监听（需要图形会话，X11 下可阻塞按键）
    # terminal: 终端内按回车说话（无图形环境/SSH 时的回退方式）
    shortcuts = [
        {
            'key': 'caps_lock',     # 监听大写锁定键
            'type': 'keyboard',
            'suppress': True,       # 阻塞按键（短按自动补发；Wayland 下建议改 False）
            'hold_mode': True,      # 长按模式：按下录音、松开识别
            'enabled': True
        },
    ]
    threshold = 0.3            # 快捷键触发阈值（秒），低于此值视为误触取消

    # ======== 输出方式 ========
    paste = False              # True=写入剪贴板模拟 Ctrl-V 粘贴；False=模拟逐字输入
    restore_clip = True        # 粘贴后是否恢复剪贴板原内容

    save_audio = True          # 是否保存录音文件到 年份/月份/assets/
    audio_name_len = 20        # 录音文件名中包含识别结果的前多少个字

    context = ''               # 提示词上下文，辅助服务端模型识别（人名、术语等）
    language = 'auto'          # 识别语言：'auto'/'chinese'/'english' 等

    trash_punc = '，。,.'       # 要消除的末尾标点
    trash_punc_thresh = 8      # 语义单元数低于该值时去除末尾标点

    traditional_convert = False      # 是否将结果转为繁体中文
    traditional_locale = 'zh-hant'   # 繁体地区: zh-hant / zh-tw / zh-hk

    # ======== 热词 ========
    hot = True                 # 启用音素热词替换（hot.txt）
    hot_thresh = 0.85          # 替换热词阈值（高）
    hot_similar = 0.6          # 相似热词阈值（低，仅提示）
    hot_rule = True            # 启用正则规则替换（hot-rule.txt）

    # ======== 日志 ========
    log_level = 'DEBUG'        # DEBUG / INFO / WARNING / ERROR

    # ======== 分段参数（与服务端协议一致）========
    mic_seg_duration = 60      # 听写分段长度（秒）
    mic_seg_overlap = 4        # 听写分段重叠（秒）

    file_seg_duration = 60     # 文件转录分段长度
    file_seg_overlap = 4       # 文件转录分段重叠

    file_save_srt = True       # 转录保存 srt 字幕
    file_save_txt = True       # 转录保存 txt 文本
    file_save_json = True      # 转录保存 json 时间戳

    # ======== Linux 平台专属 ========
    class linux:
        # 音频后端: auto -> 优先 PulseAudio，失败回退 ALSA
        audio_api = 'auto'
        input_device = None    # 输入设备索引或名称，None 为系统默认

        # 上屏工具：auto 自动探测 xdotool/wtype，找不到则退化为仅复制到剪贴板
        type_tool = 'auto'

        # 剪贴板工具：auto 自动探测 xclip/xsel/wl-copy
        clipboard_tool = 'auto'


# 快捷键可用名称（keyboard 类型）：
#   caps_lock, space, esc, f1-f12, enter, tab 以及单字符按键如 a z 0 等
# 说明：
#   - suppress=True 时短按会自动补发原按键；X11 下有效，Wayland 下无法阻塞，
#     请将 suppress 改为 False 或选用不敏感按键（如 f9）。
#   - 无图形环境（SSH/TTY）时可在 shortcuts 中加入 {'key':'enter','type':'terminal',...}
#     在终端里按回车开始说话，再次回车结束。
