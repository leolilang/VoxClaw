"""音频播放：支持 WAV 字节流、本地音频文件与 PCM 流式播放，均在线程中执行以避免阻塞事件循环。"""

import asyncio
import queue
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np
import sounddevice as sd
from loguru import logger

from config.settings import AudioConfig
from audio.device import resolve_device
from utils.audio_utils import wav_bytes_to_float


class AudioPlayer:
    def __init__(self, config: AudioConfig):
        self._device = resolve_device(config.output_device, "output")
        self._playing = False
        self._stream_stop = False

    async def play_wav_bytes(self, data: bytes):
        try:
            audio, sample_rate = wav_bytes_to_float(data)
        except Exception as e:
            logger.error("WAV 解码失败: {}", e)
            return
        await self._play(audio, sample_rate)

    async def play_file(self, path: Path | str):
        path = Path(path)
        if not path.exists():
            logger.warning("音频文件不存在: {}", path)
            return
        await self.play_wav_bytes(path.read_bytes())

    async def _play(self, audio: np.ndarray, sample_rate: int):
        self._playing = True
        try:
            await asyncio.to_thread(self._play_blocking, audio, sample_rate)
        finally:
            self._playing = False

    def _play_blocking(self, audio: np.ndarray, sample_rate: int):
        sd.play(audio, samplerate=sample_rate, device=self._device)
        sd.wait()

    async def play_pcm_stream(self, chunks: AsyncIterator[np.ndarray], sample_rate: int):
        """流式播放：边接收 float32 PCM 块边写入输出设备，收到首块即出声。"""
        buf: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=256)
        self._playing = True
        self._stream_stop = False

        def writer():
            with sd.OutputStream(
                samplerate=sample_rate, channels=1, dtype="float32", device=self._device
            ) as out:
                while True:
                    item = buf.get()
                    if item is None or self._stream_stop:
                        break
                    out.write(item.reshape(-1, 1))

        writer_task = asyncio.create_task(asyncio.to_thread(writer))
        try:
            async for chunk in chunks:
                if self._stream_stop:
                    break
                await asyncio.to_thread(buf.put, np.asarray(chunk, dtype=np.float32))
        finally:
            await asyncio.to_thread(buf.put, None)
            await writer_task
            self._playing = False

    def stop(self):
        self._stream_stop = True
        if self._playing:
            sd.stop()

    @property
    def is_playing(self) -> bool:
        return self._playing
