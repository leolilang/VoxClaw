"""Step 流式语音合成（WebSocket）客户端。

协议: wss://api.stepfun.com/v1/realtime/audio?model=<tts_model>
流程: 建联 -> tts.connection.done -> tts.create -> tts.text.delta/done
      -> 持续接收 tts.response.audio.delta（base64 PCM）边收边播。
"""

import base64
import json
from collections.abc import AsyncIterator

import numpy as np
import websockets
from loguru import logger

from config.settings import StepTTSConfig, TTSConfig
from utils.timer import Timer

TEXT_CHUNK_CHARS = 500  # 单条 tts.text.delta 上限 1000 字符，留余量


class StepTTSWebSocket:
    def __init__(self, step_config: StepTTSConfig, tts_config: TTSConfig):
        self._step = step_config
        self._tts = tts_config
        self._url = f"{tts_config.ws_endpoint}?model={step_config.tts_model}"

    @property
    def sample_rate(self) -> int:
        return self._tts.ws_sample_rate

    async def stream(self, text: str) -> AsyncIterator[np.ndarray]:
        """流式合成：逐块 yield float32 PCM 音频。"""
        timer = Timer()
        first_chunk = True
        headers = {"Authorization": f"Bearer {self._step.api_key}"}

        async with websockets.connect(
            self._url, additional_headers=headers, max_size=None
        ) as ws:
            session_id = await self._wait_connection(ws)

            await self._send(ws, "tts.create", {
                "session_id": session_id,
                "voice_id": self._tts.voice,
                "response_format": "pcm",
                "sample_rate": self._tts.ws_sample_rate,
                "speed_ratio": self._tts.speed,
                "mode": "sentence",
            })
            for i in range(0, len(text), TEXT_CHUNK_CHARS):
                await self._send(ws, "tts.text.delta", {
                    "session_id": session_id,
                    "text": text[i : i + TEXT_CHUNK_CHARS],
                })
            await self._send(ws, "tts.text.done", {"session_id": session_id})

            async for raw in ws:
                msg = json.loads(raw)
                mtype = msg.get("type", "")
                data = msg.get("data", {})

                if mtype == "tts.response.audio.delta":
                    audio_b64 = data.get("audio")
                    if audio_b64:
                        if first_chunk:
                            logger.info("TTS 首块音频延迟 {:.0f} ms", timer.elapsed_ms())
                            first_chunk = False
                        pcm = np.frombuffer(base64.b64decode(audio_b64), dtype=np.int16)
                        yield pcm.astype(np.float32) / 32768.0
                    if data.get("status") == "finished":
                        break
                elif mtype == "tts.response.audio.done":
                    audio_b64 = data.get("audio")
                    if first_chunk and audio_b64:
                        pcm = np.frombuffer(base64.b64decode(audio_b64), dtype=np.int16)
                        yield pcm.astype(np.float32) / 32768.0
                    break
                elif mtype == "tts.response.error":
                    raise RuntimeError(f"Step TTS WebSocket 错误: {data}")

        logger.info("TTS 流式合成完成，总耗时 {:.0f} ms", timer.elapsed_ms())

    async def _wait_connection(self, ws) -> str:
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == "tts.connection.done":
                return msg["data"]["session_id"]
            if msg.get("type") == "tts.response.error":
                raise RuntimeError(f"Step TTS 建联失败: {msg.get('data')}")

    @staticmethod
    async def _send(ws, mtype: str, data: dict):
        await ws.send(json.dumps({"type": mtype, "data": data}))
