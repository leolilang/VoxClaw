"""麦克风采集：sounddevice 回调线程 -> asyncio 队列，输出 float32 单声道帧。"""

import asyncio

import numpy as np
import sounddevice as sd
from loguru import logger

from config.settings import AudioConfig
from audio.device import resolve_device

QUEUE_MAX_BLOCKS = 200  # 约 6.4s @ 512/16k，满则丢弃最旧帧


class MicrophoneRecorder:
    def __init__(self, config: AudioConfig):
        self._config = config
        self._stream: sd.InputStream | None = None
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=QUEUE_MAX_BLOCKS)
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self):
        if self._stream is not None:
            return
        self._loop = asyncio.get_running_loop()
        device = resolve_device(self._config.input_device, "input")
        self._stream = sd.InputStream(
            samplerate=self._config.sample_rate,
            channels=self._config.channels,
            blocksize=self._config.block_size,
            dtype="float32",
            device=device,
            callback=self._callback,
        )
        self._stream.start()
        logger.info(
            "麦克风已启动: {} Hz, {} ch, block={}",
            self._config.sample_rate, self._config.channels, self._config.block_size,
        )

    def _callback(self, indata: np.ndarray, frames, time_info, status):
        if status:
            logger.warning("音频输入状态: {}", status)
        mono = indata.mean(axis=1) if indata.shape[1] > 1 else indata[:, 0]
        frame = mono.copy()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._enqueue, frame)

    def _enqueue(self, frame: np.ndarray):
        if self._queue.full():
            try:
                self._queue.get_nowait()  # 丢弃最旧帧，保证实时性
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait(frame)

    async def get_frame(self) -> np.ndarray:
        """获取下一帧音频（float32, [-1,1], 长度 block_size）。"""
        return await self._queue.get()

    def clear(self):
        """清空积压帧（如播放回复期间采集到的声音）。"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("麦克风已停止")
