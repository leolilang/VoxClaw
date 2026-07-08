"""对话会话：维护多轮对话历史。"""

import time
import uuid
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: float = field(default_factory=time.time)
    messages: list[Message] = field(default_factory=list)

    def add_user(self, content: str):
        self.messages.append(Message("user", content))

    def add_assistant(self, content: str):
        self.messages.append(Message("assistant", content))

    def history(self, max_messages: int) -> list[dict]:
        """返回最近 max_messages 条消息（OpenAI messages 格式）。"""
        recent = self.messages[-max_messages:] if max_messages > 0 else []
        return [{"role": m.role, "content": m.content} for m in recent]

    def reset(self):
        logger.info("会话 {} 已重置（共 {} 条消息）", self.id, len(self.messages))
        self.messages.clear()
