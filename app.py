"""VoxClaw 入口：加载配置、组装模块、运行语音助手主循环。

用法:
    python app.py [--config config/config.yaml] [--debug]
"""

import argparse
import asyncio
import sys

from assistant.pipeline import VoicePipeline
from audio.device import log_default_devices
from audio.player import AudioPlayer
from audio.recorder import MicrophoneRecorder
from config.settings import load_settings
from llm.openclaw import OpenClawClient
from stt.step_stt import StepSTT
from tts.step_tts import StepTTS
from tts.step_tts_ws import StepTTSWebSocket
from tts.xfyun_tts import XfyunTTS
from utils.logger import setup_logger
from utils.platform_info import log_runtime_environment
from vad.recorder import VADRecorder
from vad.silero import SileroVAD
from wakeword.detector import WakeWordDetector


async def main(config_path: str | None, debug: bool = False):
    settings = load_settings(config_path)
    logger = setup_logger("DEBUG" if debug else "INFO")

    if not settings.step.api_key:
        logger.warning("未配置 Step API Key（config.yaml 的 step.api_key 或环境变量 STEP_API_KEY），Step STT 将无法工作")

    log_runtime_environment()
    log_default_devices()

    mic = MicrophoneRecorder(settings.audio)
    player = AudioPlayer(settings.audio)
    wakeword = WakeWordDetector(settings.wakeword)
    vad = SileroVAD(threshold=settings.vad.threshold)
    vad_recorder = VADRecorder(
        vad, settings.vad,
        sample_rate=settings.audio.sample_rate,
        block_size=settings.audio.block_size,
    )
    stt = StepSTT(settings.step)
    chat_config = settings.resolve_llm()
    llm = OpenClawClient(chat_config)
    logger.info("LLM 使用 {} 后端（model: {}, endpoint: {}）",
                settings.llm.provider, chat_config.model, chat_config.endpoint)
    tts_ws = None
    if settings.tts.provider == "step":
        tts = StepTTS(settings.step, settings.tts)
        if settings.tts.transport == "websocket":
            tts_ws = StepTTSWebSocket(settings.step, settings.tts)
            logger.info("TTS 使用 Step 服务（transport: websocket, voice: {}）", settings.tts.voice)
        else:
            logger.info("TTS 使用 Step 服务（transport: http, voice: {}）", settings.tts.voice)
    elif settings.tts.provider == "xfyun":
        if not (settings.xfyun_tts.app_id and settings.xfyun_tts.api_key and settings.xfyun_tts.api_secret):
            logger.warning("TTS 已选择科大讯飞，但未完整配置 xfyun_tts.app_id/api_key/api_secret")
        tts = XfyunTTS(settings.xfyun_tts, settings.tts)
        tts_ws = tts
        logger.info("TTS 使用科大讯飞服务（transport: websocket, voice: {}, sample_rate: {}）", settings.xfyun_tts.voice, settings.xfyun_tts.sample_rate)
    else:
        raise ValueError(f"未知 tts.provider: {settings.tts.provider}（可选 step / xfyun）")

    pipeline = VoicePipeline(settings, mic, player, wakeword, vad_recorder, stt, llm, tts, tts_ws, debug=debug)
    try:
        await pipeline.run()
    finally:
        await pipeline.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VoxClaw 本地 AI 语音助手")
    parser.add_argument("--config", default=None, help="配置文件路径（默认 config/config.yaml）")
    parser.add_argument("--debug", action="store_true", help="输出 DEBUG 级别日志")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.config, debug=args.debug))
    except KeyboardInterrupt:
        print("\nVoxClaw 已退出")
        sys.exit(0)
