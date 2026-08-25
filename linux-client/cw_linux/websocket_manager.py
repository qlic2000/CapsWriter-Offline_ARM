# coding: utf-8
"""
WebSocket 连接管理模块（自 core/client/connection/websocket_manager.py 移植）

负责与 Windows 服务端的连接建立、自动重连、消息收发。
"""

from __future__ import annotations

import json
import asyncio
from typing import TYPE_CHECKING, Optional

import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from config_client import ClientConfig as Config
from cw_linux.protocol import AudioMessage, RecognitionMessage
from .state import console
from .logger import get_logger

if TYPE_CHECKING:
    from .state import ClientState
    from .app import CapsWriterClient

logger = get_logger('client')


class CommunicationError(Exception):
    """通信层通用异常"""
    pass


class WebSocketManager:
    """
    WebSocket 连接管理器

    Attributes:
        app: 客户端 App 实例
        max_retries: 最大重试次数（保留字段）
    """

    def __init__(self, app: 'CapsWriterClient'):
        self.app = app
        self._connect_fail_logged = False  # 断联后只记一次失败日志

    @property
    def state(self) -> 'ClientState':
        return self.app.state

    @property
    def is_connected(self) -> bool:
        return self.state.is_connected

    async def connect(self) -> bool:
        """
        建立 WebSocket 连接，失败自动重试（由上层循环驱动）

        Returns:
            连接是否成功
        """
        if self.is_connected:
            return True

        if self.state.websocket is not None:
            self.state.websocket = None

        url = "ws://%s:%s" % (Config.addr, Config.port)

        try:
            if not self._connect_fail_logged:
                logger.debug("正在连接服务端 %s" % url)

            kwargs = dict(
                uri=url,
                subprotocols=["binary"],
                max_size=None,
                max_queue=None,
            )

            # websockets>=14 默认走代理，局域网直连需显式禁用
            try:
                version = tuple(int(v) for v in websockets.__version__.split(".")[:2])
                if version >= (14,):
                    kwargs["proxy"] = None
            except Exception:
                pass

            self.state.websocket = await websockets.connect(**kwargs)

            console.print('[bold green]已连接服务端: %s[/bold green]\n' % url)
            logger.info("WebSocket 建立成功: %s" % url)
            self._connect_fail_logged = False
            return True

        except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
            if not self._connect_fail_logged:
                logger.debug("连接服务端 %s 被拒绝或超时" % url)
                self._connect_fail_logged = True
        except Exception as e:
            if not self._connect_fail_logged:
                logger.debug("连接服务端 %s 失败: %s" % (url, e))
                self._connect_fail_logged = True

        return False

    async def send(self, message: AudioMessage) -> bool:
        """发送 AudioMessage 到服务端"""
        if not self.is_connected:
            logger.warning("无法发送消息：WebSocket 未连接")
            return False

        try:
            await self.state.websocket.send(message.to_json())
            return True

        except (ConnectionClosedError, ConnectionClosedOK):
            self.state.websocket = None
            raise CommunicationError("发送失败：连接已断开")

        except Exception as e:
            raise CommunicationError("发送消息时发生未知错误: %s" % e)

    async def receive(self) -> Optional[RecognitionMessage]:
        """接收服务端 RecognitionMessage"""
        if not self.is_connected:
            logger.warning("无法接收消息：WebSocket 未连接")
            return None

        try:
            raw_message = await self.state.websocket.recv()
            data = json.loads(raw_message)
            return RecognitionMessage.from_dict(data)

        except (ConnectionClosedError, ConnectionClosedOK):
            self.state.websocket = None
            raise CommunicationError("接收失败：连接已断开")

        except json.JSONDecodeError as e:
            raise CommunicationError("消息解析失败: %s" % e)

        except Exception as e:
            raise CommunicationError("接收消息时发生未知错误: %s" % e)

    async def close(self) -> None:
        """关闭 WebSocket 连接"""
        if self.state.websocket is not None:
            await self.state.websocket.close()
            self.state.websocket = None
            logger.info("WebSocket 连接已关闭")

    def close_sync(self) -> None:
        """从同步上下文关闭连接（退出清理用）"""
        if self.state.websocket is None:
            return

        loop = self.app.loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.close(), loop)
            logger.debug("已调度 WebSocket 关闭（threadsafe）")
        else:
            self.state.websocket = None
            logger.debug("事件循环已停，直接置空 WebSocket 引用")
