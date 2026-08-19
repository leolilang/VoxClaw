"""LLM 客户端（OpenAI 兼容 chat completions 接口，支持 OpenClaw Gateway / Step API / DeepSeek API）。"""

import httpx
from loguru import logger

from assistant.session import Session
from config.settings import ChatConfig
from utils.timer import Timer


class OpenClawClient:
    def __init__(self, config: ChatConfig):
        self._config = config
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        self._client = httpx.AsyncClient(
            base_url=config.endpoint.rstrip("/"),
            headers=headers,
            timeout=config.timeout_s,
        )

    async def chat(self, session: Session, user_text: str) -> str:
        """发送用户文本，返回 AI 回复，并将本轮对话写入会话历史。"""
        messages = [{"role": "system", "content": self._config.system_prompt}]
        messages += session.history(self._config.max_history)
        messages.append({"role": "user", "content": user_text})

        timer = Timer()
        resp = await self._client.post(
            "/v1/chat/completions",
            json={"model": self._config.model, "messages": messages},
        )
        if resp.status_code >= 400:
            logger.warning(
                "LLM 请求失败 [{}] model={} endpoint={}: {}",
                resp.status_code,
                self._config.model,
                self._config.endpoint,
                resp.text[:500],
            )
        resp.raise_for_status()
        reply = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        logger.info("OpenClaw 回复 ({:.0f} ms): {!r}", timer.elapsed_ms(), reply)

        session.add_user(user_text)
        session.add_assistant(reply)
        return reply

    async def close(self):
        await self._client.aclose()
