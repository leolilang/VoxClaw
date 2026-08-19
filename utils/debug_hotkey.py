"""DEBUG 模式下的手动唤醒热键监听。"""

import asyncio
from typing import Callable

from loguru import logger


class ManualWakeHotkey:
    """使用全局热键触发 asyncio.Event，便于跳过唤醒词验证后续链路。"""

    def __init__(self, hotkey: str):
        self._hotkey = hotkey
        self._event = asyncio.Event()
        self._listener = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def event(self) -> asyncio.Event:
        return self._event

    def start(self):
        if self._listener is not None:
            return
        try:
            from pynput import keyboard
        except ImportError:
            logger.warning("未安装 pynput，DEBUG 手动唤醒热键不可用；请运行 pip install -r requirements.txt")
            return

        self._loop = asyncio.get_running_loop()

        def trigger():
            if self._loop is None or self._loop.is_closed():
                return
            self._loop.call_soon_threadsafe(self._event.set)

        try:
            hotkeys: dict[str, Callable[[], None]] = {self._hotkey: trigger}
            self._listener = keyboard.GlobalHotKeys(hotkeys)
            self._listener.start()
        except Exception as exc:
            self._listener = None
            logger.warning("DEBUG 手动唤醒热键启动失败：{}", exc)
            return
        logger.info("DEBUG 手动唤醒已启用：按 {} 跳过唤醒词", self._hotkey)

    def stop(self):
        if self._listener is None:
            return
        self._listener.stop()
        self._listener = None
