"""基于 VAD 的自动录音：等待开口 -> 录音 -> 静音判定结束。"""

import numpy as np
from loguru import logger

from audio.recorder import MicrophoneRecorder
from audio.ring_buffer import RingBuffer
from config.settings import VADConfig
from vad.silero import SileroVAD


class VADRecorder:
    def __init__(self, vad: SileroVAD, config: VADConfig, sample_rate: int, block_size: int):
        self._vad = vad
        self._config = config
        self._sample_rate = sample_rate
        self._block_size = block_size
        self._block_ms = block_size / sample_rate * 1000

    async def record(
        self, mic: MicrophoneRecorder, timeout_s: float | None = None
    ) -> np.ndarray | None:
        """录制一段语音，返回 float32 音频；等待开口超时则返回 None。

        timeout_s: 等待开口的超时时间，None 时使用配置的 speech_timeout_s。
        """
        speech_timeout_s = timeout_s if timeout_s is not None else self._config.speech_timeout_s
        self._vad.reset()
        pre_roll_blocks = max(1, int(self._config.pre_roll_ms / self._block_ms))
        pre_roll = RingBuffer(pre_roll_blocks * self._block_size)

        # 阶段一：等待用户开口
        waited_ms = 0.0
        while True:
            frame = await mic.get_frame()
            if self._vad.is_speech(frame):
                break
            pre_roll.write(frame)
            waited_ms += self._block_ms
            if waited_ms >= speech_timeout_s * 1000:
                logger.info("等待开口超时（{:.1f}s），返回待机", speech_timeout_s)
                return None

        logger.info("检测到语音，开始录音")
        segments = [pre_roll.read_all(), frame]

        # 阶段二：录音直到静音或超长
        silence_ms = 0.0
        recorded_ms = self._block_ms
        while True:
            frame = await mic.get_frame()
            segments.append(frame)
            recorded_ms += self._block_ms

            if self._vad.is_speech(frame):
                silence_ms = 0.0
            else:
                silence_ms += self._block_ms
                if silence_ms >= self._config.silence_ms:
                    break

            if recorded_ms >= self._config.max_record_s * 1000:
                logger.warning("录音达到最大时长 {:.0f}s，强制结束", self._config.max_record_s)
                break

        audio = np.concatenate(segments)
        logger.info("录音结束，时长 {:.2f}s", len(audio) / self._sample_rate)
        return audio
