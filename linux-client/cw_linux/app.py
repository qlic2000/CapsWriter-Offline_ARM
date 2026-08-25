# coding: utf-8
"""
CapsWriter Offline Linux 客户端门面类 (Facade)

自 core/client/app.py 精简移植：
- 移除托盘、LLM、UDP 组件
- 保留：状态、热词、WebSocket、音频流、快捷键、输出、日记
- 根据命令行参数自动选择 麦克风模式 / 文件转录模式
"""

import os
import sys
import signal
import asyncio
from pathlib import Path

from .state import ClientState, console
from .logger import get_logger
from config_client import ClientConfig as Config, __version__

from .websocket_manager import WebSocketManager
from .audio.stream import AudioStreamManager
from .hotkey.hotkey_manager import HotkeyManager
from .hotword.manager import HotwordManager
from .output.text_output import TextOutput
from .output.clipboard import copy_to_clipboard

logger = get_logger('client')


class CapsWriterClient:
    """
    CapsWriter Linux 客户端门面类

    外部接口：start()。内部管理异步循环与资源生命周期。
    """

    def __init__(self):
        # 切换到程序根目录（音频/日记按相对路径存放）
        self.base_dir = Path(__file__).parents[1]
        os.chdir(self.base_dir)

        # 事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # 共享状态
        self.state = ClientState(app=self)

        # 热词管理器
        self.hotword = HotwordManager(
            hotword_files=None,
            threshold=Config.hot_thresh,
            similar_threshold=Config.hot_similar
        )

        # 连接/硬件/输出组件
        self.ws = WebSocketManager(self)
        self.output = TextOutput()
        self.stream = AudioStreamManager(self)
        self.shortcut = HotkeyManager(self, list(Config.shortcuts))

    def stop(self):
        """
        统一释放资源（顺序：快捷键 -> 音频 -> 热词 -> WebSocket -> State）
        """
        logger.info("正在执行 CapsWriterClient 资源释放...")

        try:
            self.shortcut.stop()
        except Exception as e:
            logger.debug("停止快捷键出错: %s" % e)

        try:
            self.stream.stop()
        except Exception as e:
            logger.debug("停止音频流出错: %s" % e)

        try:
            self.hotword.stop()
        except Exception as e:
            logger.debug("停止热词监视出错: %s" % e)

        try:
            self.ws.close_sync()
        except Exception as e:
            logger.debug("关闭 WebSocket 出错: %s" % e)

        try:
            self.state.reset()
        except Exception as e:
            logger.warning("重置状态时发生错误: %s" % e)

        try:
            self.loop.stop()
        except Exception:
            pass

        logger.info("资源释放完成")
        console.print('[green4]再见！')

    def _register_signal(self):
        """注册 SIGINT/SIGTERM 退出处理"""
        def _handler(signum, frame):
            name = signal.Signals(signum).name if hasattr(signal, 'Signals') else signum
            print("\n收到 %s，正在退出...\n" % name)
            self.stop()
            sys.exit(0)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except Exception:
                pass

    def _show_mic_tips(self):
        """显示麦克风模式提示"""
        enabled = [sc['key'] for sc in Config.shortcuts if sc.get('enabled', True)]
        console.rule('[bold #d55252]CapsWriter Offline Client (Linux)[/]')
        console.print('\n版本：[bold green]%s[/]' % __version__)
        console.print(f'\n当前基文件夹：[cyan underline]{os.getcwd()}[/]')
        console.print(f'服务端地址： [cyan underline]{Config.addr}:{Config.port}[/]')
        console.print(f'当前所用快捷键：[green4]{"、".join(enabled)}[/]')
        console.print(
            '\n使用方式：按住快捷键说话，松开即上屏；'
            '音视频文件可拖入终端执行 python3 start_client.py 文件名 转录字幕\n'
        )
        console.rule()

    async def _run_mic(self):
        """麦克风实时听写模式主循环"""
        logger.info("=" * 50)
        logger.info("CapsWriter Offline Linux Client %s (麦克风模式)" % __version__)
        logger.info("日志级别: %s" % Config.log_level)

        self._show_mic_tips()

        # 启动音频流与快捷键监听
        self.stream.start()
        self.shortcut.start()

        # 加载热词并启动文件监视
        self.hotword.start()

        # 结果接收主循环（含自动重连）
        exit_flag = asyncio.Event()
        from cw_linux.protocol import RecognitionMessage

        while not exit_flag.is_set():
            if not await self.ws.connect():
                await asyncio.sleep(2)
                continue

            while True:
                try:
                    message = await self.ws.receive()
                    if message is None:
                        break
                    await self._handle_message(message)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.debug("连接异常中断: %s" % e)
                    break

            console.print('[bold red]已断开服务端连接，2秒后重连...[/bold red]\n')
            await asyncio.sleep(2)

    async def _handle_message(self, message: RecognitionMessage) -> None:
        """处理服务端识别结果"""
        from .protocol import RecognitionMessage  # noqa: F401 类型引用

        text = message.text
        original_text = text
        delay = message.time_complete - message.time_submit

        if not message.is_final:
            return

        logger.info("收到最终识别结果: %s, 时延: %.2fs" % (text, delay))

        # 繁体转换（可选）
        if getattr(Config, 'traditional_convert', False):
            try:
                from .transcribe.zhconv import convert as zhconv_convert
                text = zhconv_convert(text, Config.traditional_locale)
            except Exception as e:
                logger.warning("繁体转换失败: %s" % e)

        # 1. 音素热词替换
        hotword_start = time.monotonic() if False else None
        import time as _time
        hotword_start = _time.monotonic()

        correction_result = self.hotword.get_phoneme_corrector().correct(text, k=10)
        if Config.hot:
            text = correction_result.text

        # 2. 去掉末尾标点
        text = TextOutput.strip_punc(text)

        # 3. 规则替换
        if Config.hot_rule:
            text = self.hotword.get_rule_corrector().substitute(text)

        hotword_elapsed = _time.monotonic() - hotword_start

        # 控制台输出
        console.print('任务标识：%s' % message.task_id)
        console.print('    录音时长：%.2fs' % message.duration)
        hotword_label = '  热词时延: %.2fs' % hotword_elapsed if Config.hot else ''
        console.print('    转录时延：%.2fs%s' % (delay, hotword_label))

        original_stripped = TextOutput.strip_punc(original_text)
        console.print('    识别结果：[green]%s' % original_stripped)

        if original_stripped != text:
            console.print('    热词替换：[cyan]%s' % text)

        matched_hotwords = correction_result.matches
        potential_hotwords = correction_result.similars

        if matched_hotwords and Config.hot:
            replaced_info = ["%s->[green4]%s[/]" % (o, h) for o, h, s in matched_hotwords]
            console.print('    完全匹配：%s' % ", ".join(replaced_info))

        if potential_hotwords and Config.hot:
            replaced_set = {h for o, h, s in matched_hotwords}
            potential_matches = [(o, h, s) for o, h, s in potential_hotwords if h not in replaced_set]
            if potential_matches:
                log_str = "; ".join(["%s->%s(%.2f)" % (o, h, s) for o, h, s in potential_matches])
                logger.debug("潜在热词: %s" % log_str)

        # 输出文本
        await self.output.output(text)
        self.state.set_output_text(text)

        # 重命名录音文件 + 写日记
        if getattr(Config, 'save_audio', False):
            file_path = self.state.pop_audio_file(message.task_id)
            file_audio = None
            if file_path and file_path.exists():
                from .audio.file_manager import AudioFileManager
                fm = AudioFileManager()
                fm.file_path = file_path
                file_audio = fm.rename(text, message.time_start)

            try:
                self._write_diary(text, message.time_start, file_audio)
            except Exception as e:
                logger.warning("写入日记失败: %s" % e)

        console.line()

    def _write_diary(self, text: str, time_start: float, file_audio=None) -> None:
        """按日期归档识别结果到 年/月/日.md"""
        import time as _time
        from os import makedirs

        local_time = _time.localtime(time_start)
        time_year = _time.strftime('%Y', local_time)
        time_month = _time.strftime('%m', local_time)
        time_day = _time.strftime('%d', local_time)
        time_hms = _time.strftime('%H:%M:%S', local_time)

        folder_path = self.base_dir / time_year / time_month
        makedirs(folder_path, exist_ok=True)

        file_md = folder_path / ('%s.md' % time_day)

        if not file_md.exists():
            with open(file_md, 'w', encoding='utf-8') as f:
                f.write('')

        if file_audio:
            try:
                path_rel = file_audio.relative_to(file_md.parent).as_posix().replace(" ", "%20")
                entry = '[%s](%s) %s\n\n' % (time_hms, path_rel, text)
            except ValueError:
                entry = '%s %s\n\n' % (time_hms, text)
        else:
            entry = '%s %s\n\n' % (time_hms, text)

        with open(file_md, 'a', encoding='utf-8') as f:
            f.write(entry)

        logger.debug("写入日记: %s" % file_md.name)

    async def _run_files(self, files):
        """文件转录模式"""
        from .transcribe.file_transcriber import FileTranscriber

        console.print(f'\n版本：[bold green]{__version__}[/]')
        console.print(f'服务端地址：[cyan underline]{Config.addr}:{Config.port}[/]\n')

        logger.info("待处理文件: %s" % [str(f) for f in files])

        self.hotword.start()

        try:
            for file in files:
                logger.info("正在处理文件: %s" % file)
                transcriber = FileTranscriber(self, file)
                if await transcriber.check():
                    await transcriber.send()
                    await transcriber.receive()
                    await transcriber.close()
                logger.info("文件处理完成: %s" % file)

            logger.info("所有文件已处理完成")

            try:
                input('\n按回车退出\n')
            except EOFError:
                pass

        except Exception as e:
            logger.error("文件转录运行异常: %s" % e, exc_info=True)
            raise
        finally:
            self.hotword.stop()

    def start(self):
        """
        启动客户端（唯一入口）

        命令行带文件参数时进入文件转录模式，否则进入麦克风模式。
        """
        self._register_signal()

        files = []
        for arg in sys.argv[1:]:
            p = Path(arg)
            if p.exists():
                files.append(p.resolve())
            else:
                console.print('[yellow]忽略不存在的文件：%s[/yellow]' % arg)

        try:
            if files:
                runner = self._run_files(files)
            else:
                runner = self._run_mic()

            self.loop.run_until_complete(runner)
        except (KeyboardInterrupt, RuntimeError):
            pass
        finally:
            self.stop()
