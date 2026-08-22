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
from stt.tencent_stt import TencentSTT
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

    if settings.stt.provider == "step" and not settings.stt.step.api_key:
        logger.warning("STT 已选择 Step，但未配置 stt.step.api_key 或环境变量 STEP_API_KEY")
    if settings.stt.provider == "tencent" and not (settings.stt.tencent.secret_id and settings.stt.tencent.secret_key):
        logger.warning("STT 已选择腾讯云，但未完整配置 stt.tencent.secret_id/secret_key")

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
    if settings.stt.provider == "step":
        stt = StepSTT(settings.stt.step)
        logger.info("STT 使用 Step 服务（model: {}, endpoint: {}）", settings.stt.step.stt_model, settings.stt.step.stt_endpoint)
    elif settings.stt.provider == "tencent":
        stt = TencentSTT(settings.stt.tencent)
        logger.info("STT 使用腾讯云服务（engine: {}, region: {}）", settings.stt.tencent.engine_model_type, settings.stt.tencent.region)
    else:
        raise ValueError(f"未知 stt.provider: {settings.stt.provider}（可选 step / tencent）")
    chat_config = settings.resolve_llm()
    llm = OpenClawClient(chat_config)
    logger.info("LLM 使用 {} 后端（model: {}, endpoint: {}, api_path: {}）",
                settings.llm.provider, chat_config.model, chat_config.endpoint, chat_config.api_path)
    tts_ws = None
    if settings.tts.provider == "step":
        tts = StepTTS(settings.tts.step, settings.tts)
        if settings.tts.transport == "websocket":
            tts_ws = StepTTSWebSocket(settings.tts.step, settings.tts)
            logger.info("TTS 使用 Step 服务（transport: websocket, voice: {}）", settings.tts.voice)
        else:
            logger.info("TTS 使用 Step 服务（transport: http, voice: {}）", settings.tts.voice)
    elif settings.tts.provider == "xfyun":
        xfyun_tts = settings.tts.xfyun
        if not (xfyun_tts.app_id and xfyun_tts.api_key and xfyun_tts.api_secret):
            logger.warning("TTS 已选择科大讯飞，但未完整配置 tts.xfyun.app_id/api_key/api_secret")
        tts = XfyunTTS(xfyun_tts, settings.tts)
        tts_ws = tts
        logger.info("TTS 使用科大讯飞服务（transport: websocket, voice: {}, sample_rate: {}）", xfyun_tts.voice, xfyun_tts.sample_rate)
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
