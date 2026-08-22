"""科大讯飞 WebAPI 语音合成（TTS）客户端。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import wave
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from email.utils import format_datetime
from io import BytesIO
from urllib.parse import quote, urlencode, urlparse

import websockets
import numpy as np
from loguru import logger

from config.settings import TTSConfig, XfyunTTSConfig
from utils.timer import Timer


class XfyunTTS:
    def __init__(self, xfyun_config: XfyunTTSConfig, tts_config: TTSConfig):
        self._xfyun = xfyun_config
        self._tts = tts_config

    @property
    def sample_rate(self) -> int:
        return self._xfyun.sample_rate

    async def synthesize(self, text: str) -> bytes:
        """文本转语音，返回 WAV 音频字节流。"""
        pcm_chunks = []
        async for chunk in self.stream(text):
            pcm = np.clip(chunk, -1.0, 1.0)
            pcm_chunks.append((pcm * 32767).astype(np.int16).tobytes())
        return pcm_to_wav_bytes(b"".join(pcm_chunks), self._xfyun.sample_rate)

    async def stream(self, text: str) -> AsyncIterator[np.ndarray]:
        """流式合成：逐块 yield float32 PCM 音频。"""
        if not self._xfyun.app_id or not self._xfyun.api_key or not self._xfyun.api_secret:
            raise RuntimeError("未配置讯飞 TTS app_id/api_key/api_secret")

        timer = Timer()
        first_chunk = True
        url = self._build_auth_url()
        payload = {
            "common": {"app_id": self._xfyun.app_id},
            "business": {
                "aue": "raw",
                "auf": f"audio/L16;rate={self._xfyun.sample_rate}",
                "vcn": self._xfyun.voice,
                "speed": self._xfyun.speed,
                "volume": self._xfyun.volume,
                "pitch": self._xfyun.pitch,
                "tte": "UTF8",
            },
            "data": {
                "status": 2,
                "text": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            },
        }

        async with websockets.connect(url, max_size=None, open_timeout=self._xfyun.timeout_s) as ws:
            await ws.send(json.dumps(payload, ensure_ascii=False))
            async for raw_message in ws:
                message = json.loads(raw_message)
                logger.debug("讯飞 TTS 原始返回: {}", raw_message)
                code = message.get("code", 0)
                if code != 0:
                    raise RuntimeError(f"讯飞 TTS 合成失败 [{code}]: {message.get('message') or message}")

                data = message.get("data") or {}
                audio_b64 = data.get("audio")
                if audio_b64:
                    pcm = np.frombuffer(base64.b64decode(audio_b64), dtype=np.int16)
                    if first_chunk:
                        logger.info("讯飞 TTS 首块音频延迟 {:.0f} ms", timer.elapsed_ms())
                        first_chunk = False
                    yield pcm.astype(np.float32) / 32768.0
                if data.get("status") == 2:
                    break

        logger.info("讯飞 TTS 流式合成完成，总耗时 {:.0f} ms", timer.elapsed_ms())

    def _build_auth_url(self) -> str:
        parsed = urlparse(self._xfyun.endpoint)
        host = parsed.netloc
        path = parsed.path or "/v2/tts"
        date = format_datetime(datetime.now(timezone.utc), usegmt=True)
        signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
        signature_sha = hmac.new(
            self._xfyun.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_sha).decode("ascii")
        authorization_origin = (
            f'api_key="{self._xfyun.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("ascii")
        query = urlencode({"authorization": authorization, "date": date, "host": host}, quote_via=quote)
        separator = "&" if parsed.query else "?"
        return f"{self._xfyun.endpoint}{separator}{query}"

    async def close(self):
        return None


def pcm_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()
