"""Step 语音识别（STT）客户端。"""

import httpx
import numpy as np
from loguru import logger

from config.settings import StepSTTConfig
from utils.audio_utils import float_to_wav_bytes
from utils.timer import Timer


class StepSTT:
    def __init__(self, config: StepSTTConfig):
        self._config = config
        self._client = httpx.AsyncClient(timeout=30.0)

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """上传音频，返回识别文本。"""
        wav = float_to_wav_bytes(audio, sample_rate)
        timer = Timer()
        resp = await self._client.post(
            self._config.stt_endpoint,
            headers={"Authorization": f"Bearer {self._config.api_key}"},
            files={"file": ("speech.wav", wav, "audio/wav")},
            data={"model": self._config.stt_model, "response_format": "json"},
        )
        if resp.status_code >= 400:
            if resp.status_code == 400 and "no speech found" in resp.text.lower():
                logger.info("STT 未检测到语音 ({:.0f} ms)，跳过本轮", timer.elapsed_ms())
                return ""
            logger.error("STT 请求失败 [{}]: {}", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        text = (resp.json().get("text") or "").strip()
        logger.info("STT 结果 ({:.0f} ms): {!r}", timer.elapsed_ms(), text)
        return text

    async def close(self):
        await self._client.aclose()
