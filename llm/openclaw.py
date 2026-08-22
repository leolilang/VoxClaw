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

        reply = await self._chat_completion(messages, label="OpenClaw 回复")
        session.add_user(user_text)
        session.add_assistant(reply)
        return reply

    async def complete(self, system_prompt: str, user_text: str, label: str = "LLM 回复") -> str:
        """发送一次性提示词，返回回复；不写入会话历史。"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        return await self._chat_completion(messages, label=label)

    async def _chat_completion(self, messages: list[dict], label: str) -> str:
        timer = Timer()
        resp = await self._client.post(
            self._config.api_path,
            json={"model": self._config.model, "messages": messages},
        )
        logger.debug(
            "LLM 原始返回 [{}] model={} endpoint={} api_path={} label={} body={}",
            resp.status_code,
            self._config.model,
            self._config.endpoint,
            self._config.api_path,
            label,
            resp.text,
        )
        if resp.status_code >= 400:
            logger.warning(
                "LLM 请求失败 [{}] model={} endpoint={} api_path={}: {}",
                resp.status_code,
                self._config.model,
                self._config.endpoint,
                self._config.api_path,
                resp.text[:500],
            )
        resp.raise_for_status()
        reply = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        logger.info("{} ({:.0f} ms): {!r}", label, timer.elapsed_ms(), reply)
        return reply

    async def close(self):
        await self._client.aclose()
