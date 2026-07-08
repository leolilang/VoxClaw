"""Step 语音合成（TTS）客户端。"""

import httpx
from loguru import logger

from config.settings import StepConfig, TTSConfig
from utils.timer import Timer


class StepTTS:
    def __init__(self, step_config: StepConfig, tts_config: TTSConfig):
        self._step = step_config
        self._tts = tts_config
        self._client = httpx.AsyncClient(timeout=60.0)

    async def synthesize(self, text: str) -> bytes:
        """文本转语音，返回 WAV 音频字节流。"""
        timer = Timer()
        resp = await self._client.post(
            self._step.tts_endpoint,
            headers={"Authorization": f"Bearer {self._step.api_key}"},
            json={
                "model": self._step.tts_model,
                "input": text,
                "voice": self._tts.voice,
                "speed": self._tts.speed,
                "response_format": "wav",
            },
        )
        resp.raise_for_status()
        logger.info("TTS 合成完成 ({:.0f} ms, {} bytes)", timer.elapsed_ms(), len(resp.content))
        return resp.content

    async def close(self):
        await self._client.aclose()
