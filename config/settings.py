"""配置加载：YAML + 环境变量（STEP_API_KEY 优先于文件配置）。"""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 512
    input_device: int | str | None = None
    output_device: int | str | None = None


class WakeWordConfig(BaseModel):
    model: str = "hey_jarvis"
    threshold: float = 0.45
    cooldown_s: float = 2.0


class VADConfig(BaseModel):
    threshold: float = 0.55
    silence_ms: int = 500
    speech_timeout_s: float = 6.0
    max_record_s: float = 15.0
    pre_roll_ms: int = 300


class ConversationConfig(BaseModel):
    mode: str = "multi"  # single=单轮（答完回待机）/ multi=多轮（答完继续听追问）
    follow_up_timeout_s: float = 10.0  # 多轮模式下等待追问的时长
    # 退出指令词：识别文本命中时结束对话回待机（短句包含即生效）
    exit_words: list[str] = ["关闭", "退下", "关机", "停止", "退出", "再见", "闭嘴", "休眠"]


class DebugConfig(BaseModel):
    manual_wake_hotkey: str = "<shift>+<ctrl>+i"


class StepConfig(BaseModel):
    api_key: str = ""
    stt_endpoint: str = "https://api.stepfun.com/v1/audio/transcriptions"
    tts_endpoint: str = "https://api.stepfun.com/v1/audio/speech"
    stt_model: str = "step-asr"
    tts_model: str = "step-tts-mini"


class LLMEndpointConfig(BaseModel):
    endpoint: str = ""
    api_key: str = ""
    model: str = ""


class LLMConfig(BaseModel):
    provider: str = "openclaw"  # openclaw=本地 OpenClaw Gateway / stepfun=Step API 直连 / deepseek=DeepSeek API
    timeout_s: float = 60.0
    max_history: int = 20
    system_prompt: str = "你是 VoxClaw 语音助手。回答要简洁口语化，适合语音播报。"
    openclaw: LLMEndpointConfig = LLMEndpointConfig(
        endpoint="http://127.0.0.1:18789", model="openclaw"
    )
    stepfun: LLMEndpointConfig = LLMEndpointConfig(
        endpoint="https://api.stepfun.com", model="step-3.5-flash"
    )
    deepseek: LLMEndpointConfig = LLMEndpointConfig(
        endpoint="https://api.deepseek.com", model="deepseek-chat"
    )


class ChatConfig(BaseModel):
    """由 LLMConfig 按 provider 解析出的最终 LLM 客户端配置。"""

    endpoint: str
    api_key: str = ""
    model: str
    timeout_s: float = 60.0
    max_history: int = 20
    system_prompt: str = ""


class TTSConfig(BaseModel):
    voice: str = "wenrounvsheng"
    speed: float = 1.0
    transport: str = "websocket"  # websocket=流式低延迟 / http=整段合成
    ws_endpoint: str = "wss://api.stepfun.com/v1/realtime/audio"
    ws_sample_rate: int = 24000


class Settings(BaseModel):
    audio: AudioConfig = AudioConfig()
    wakeword: WakeWordConfig = WakeWordConfig()
    vad: VADConfig = VADConfig()
    conversation: ConversationConfig = ConversationConfig()
    debug: DebugConfig = DebugConfig()
    step: StepConfig = StepConfig()
    llm: LLMConfig = LLMConfig()
    tts: TTSConfig = TTSConfig()

    def resolve_llm(self) -> ChatConfig:
        if self.llm.provider not in ("openclaw", "stepfun", "deepseek"):
            raise ValueError(f"未知的 llm.provider: {self.llm.provider}（可选 openclaw / stepfun / deepseek）")
        ep = getattr(self.llm, self.llm.provider)
        api_key = ep.api_key
        if not api_key and self.llm.provider == "stepfun":
            api_key = self.step.api_key  # stepfun 直连时默认复用 step.api_key
        return ChatConfig(
            endpoint=ep.endpoint,
            api_key=api_key,
            model=ep.model,
            timeout_s=self.llm.timeout_s,
            max_history=self.llm.max_history,
            system_prompt=self.llm.system_prompt,
        )


def load_settings(path: Path | str | None = None) -> Settings:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    data: dict = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    settings = Settings.model_validate(data)

    env_key = os.environ.get("STEP_API_KEY") or os.environ.get("VOXCLAW_STEP_API_KEY")
    if env_key:
        settings.step.api_key = env_key
    openclaw_key = os.environ.get("OPENCLAW_API_KEY")
    if openclaw_key:
        settings.llm.openclaw.api_key = openclaw_key
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        settings.llm.deepseek.api_key = deepseek_key
    return settings
