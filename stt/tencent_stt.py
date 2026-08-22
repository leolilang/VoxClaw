"""腾讯云一句话语音识别（ASR）客户端。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
import numpy as np
from loguru import logger

from config.settings import TencentSTTConfig
from utils.audio_utils import float_to_wav_bytes
from utils.timer import Timer

SERVICE = "asr"
ACTION = "SentenceRecognition"
VERSION = "2019-06-14"
ALGORITHM = "TC3-HMAC-SHA256"


class TencentSTT:
    def __init__(self, config: TencentSTTConfig):
        self._config = config
        self._client = httpx.AsyncClient(timeout=config.timeout_s)

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """上传音频，返回识别文本。"""
        if not self._config.secret_id or not self._config.secret_key:
            raise RuntimeError("未配置腾讯云 STT secret_id/secret_key")

        wav = float_to_wav_bytes(audio, sample_rate)
        payload = {
            "ProjectId": self._config.project_id,
            "SubServiceType": self._config.sub_service_type,
            "EngSerViceType": self._config.engine_model_type,
            "SourceType": 1,
            "VoiceFormat": self._config.voice_format,
            "UsrAudioKey": str(uuid.uuid4()),
            "Data": base64.b64encode(wav).decode("ascii"),
            "DataLen": len(wav),
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        timestamp = int(time.time())
        headers = self._build_headers(body, timestamp)

        timer = Timer()
        resp = await self._client.post(self._config.endpoint, headers=headers, content=body)
        logger.debug("腾讯云 STT 原始返回 [{}]: {}", resp.status_code, resp.text)
        if resp.status_code >= 400:
            logger.error("腾讯云 STT 请求失败 [{}]: {}", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json().get("Response", {})
        if "Error" in data:
            error = data["Error"]
            message = error.get("Message") or error
            code = error.get("Code") or "Unknown"
            if "no speech" in str(message).lower() or "silent" in str(message).lower():
                logger.info("腾讯云 STT 未检测到语音 ({:.0f} ms)，跳过本轮", timer.elapsed_ms())
                return ""
            raise RuntimeError(f"腾讯云 STT 识别失败 [{code}]: {message}")
        text = (data.get("Result") or "").strip()
        logger.info("腾讯云 STT 结果 ({:.0f} ms): {!r}", timer.elapsed_ms(), text)
        return text

    def _build_headers(self, body: str, timestamp: int) -> dict[str, str]:
        parsed = urlparse(self._config.endpoint)
        host = parsed.netloc
        date = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
        content_type = "application/json; charset=utf-8"
        canonical_request = "\n".join(
            [
                "POST",
                "/",
                "",
                f"content-type:{content_type}\n" f"host:{host}\n",
                "content-type;host",
                hashlib.sha256(body.encode("utf-8")).hexdigest(),
            ]
        )
        credential_scope = f"{date}/{SERVICE}/tc3_request"
        string_to_sign = "\n".join(
            [
                ALGORITHM,
                str(timestamp),
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        secret_date = hmac_sha256(("TC3" + self._config.secret_key).encode("utf-8"), date)
        secret_service = hmac_sha256(secret_date, SERVICE)
        secret_signing = hmac_sha256(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"{ALGORITHM} Credential={self._config.secret_id}/{credential_scope}, "
            f"SignedHeaders=content-type;host, Signature={signature}"
        )
        return {
            "Authorization": authorization,
            "Content-Type": content_type,
            "Host": host,
            "X-TC-Action": ACTION,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": VERSION,
            "X-TC-Region": self._config.region,
        }

    async def close(self):
        await self._client.aclose()


def hmac_sha256(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()
