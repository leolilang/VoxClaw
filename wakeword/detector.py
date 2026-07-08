"""唤醒词检测：累积音频帧，按 openWakeWord 要求的块大小推理并做阈值判断。"""

import time

import numpy as np
from loguru import logger

from config.settings import WakeWordConfig
from utils.audio_utils import float_to_int16
from wakeword.model import load_wakeword_model

OWW_CHUNK = 1280  # openWakeWord 推荐块大小：80ms @ 16kHz
SAMPLE_RATE = 16000
WARMUP_S = 4.0  # oww reset 后 feature_buffer 是 4s 随机噪声嵌入，需用静音冲刷，否则最初几秒检测失灵


class WakeWordDetector:
    def __init__(self, config: WakeWordConfig):
        self._config = config
        self._model = load_wakeword_model(config.model)
        self._pending = np.empty(0, dtype=np.int16)
        self._last_trigger = 0.0
        self._warm_up()

    def process(self, frame: np.ndarray) -> bool:
        """输入 float32 帧，累积到一个推理块后检测；触发唤醒时返回 True。"""
        self._pending = np.concatenate([self._pending, float_to_int16(frame)])

        triggered = False
        while len(self._pending) >= OWW_CHUNK:
            chunk, self._pending = self._pending[:OWW_CHUNK], self._pending[OWW_CHUNK:]
            prediction = self._model.predict(chunk)
            score = max(prediction.values())
            if score >= 0.1:
                logger.debug("唤醒词分数: {:.3f}（阈值 {}）", score, self._config.threshold)
            if score >= self._config.threshold and self._cooldown_passed():
                logger.info("检测到唤醒词 (score={:.2f})", score)
                self._last_trigger = time.monotonic()
                triggered = True
        if triggered:
            self.reset()
        return triggered

    def _cooldown_passed(self) -> bool:
        return time.monotonic() - self._last_trigger >= self._config.cooldown_s

    def reset(self):
        self._model.reset()
        self._pending = np.empty(0, dtype=np.int16)
        self._warm_up()

    def _warm_up(self):
        silence = np.zeros(OWW_CHUNK, dtype=np.int16)
        for _ in range(int(WARMUP_S * SAMPLE_RATE / OWW_CHUNK)):
            self._model.predict(silence)
