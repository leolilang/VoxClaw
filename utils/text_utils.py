"""TTS 前的文本清理：去除 Markdown 标记与 emoji，避免被逐字朗读。"""

import re

_MD_PATTERNS = [
    (re.compile(r"```.*?```", re.S), " "),          # 代码块
    (re.compile(r"`([^`]*)`"), r"\1"),               # 行内代码
    (re.compile(r"\*\*([^*]*)\*\*"), r"\1"),         # 粗体
    (re.compile(r"\*([^*]*)\*"), r"\1"),             # 斜体
    (re.compile(r"__([^_]*)__"), r"\1"),
    (re.compile(r"~~([^~]*)~~"), r"\1"),
    (re.compile(r"!?\[([^\]]*)\]\([^)]*\)"), r"\1"), # 链接/图片
    (re.compile(r"^#{1,6}\s*", re.M), ""),           # 标题
    (re.compile(r"^\s*[-*+]\s+", re.M), ""),         # 无序列表
    (re.compile(r"^\s*>\s?", re.M), ""),             # 引用
]

_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U0000FE00-\U0000FE0F"
    "]+",
    re.UNICODE,
)


def clean_for_tts(text: str) -> str:
    for pattern, repl in _MD_PATTERNS:
        text = pattern.sub(repl, text)
    text = _EMOJI.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


_PUNCT = re.compile(r"[\s，。！？、,.!?;；:：\"'“”‘’]+")

EXIT_MATCH_MAX_CHARS = 6  # 短句包含退出词才算数，避免长句（如"帮我关闭客厅的灯"）误判


def is_exit_command(text: str, exit_words: list[str]) -> bool:
    """判断识别文本是否为退出指令：完全等于退出词，或短句中包含退出词。"""
    cleaned = _PUNCT.sub("", text)
    if not cleaned:
        return False
    for word in exit_words:
        if cleaned == word:
            return True
        if len(cleaned) <= EXIT_MATCH_MAX_CHARS and word in cleaned:
            return True
    return False
