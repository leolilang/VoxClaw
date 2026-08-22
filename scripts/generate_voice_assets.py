"""用配置的 TTS 服务生成语音提示音（使用 config.yaml 中的音色与文案）。

生成:
    assets/greeting.wav  启动问候
    assets/wake.wav      唤醒应答
    assets/error.wav     识别失败
    assets/sleep.wav     退出应答

用法: python scripts/generate_voice_assets.py [--config config/config.yaml]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import load_settings
from tts.step_tts import StepTTS
from tts.xfyun_tts import XfyunTTS

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


async def generate(config_path: str | None):
    settings = load_settings(config_path)
    if settings.tts.provider == "step":
        if not settings.tts.step.api_key:
            sys.exit("未配置 tts.step.api_key，无法调用 Step TTS")
        tts = StepTTS(settings.tts.step, settings.tts)
        voice_label = settings.tts.voice
    elif settings.tts.provider == "xfyun":
        xfyun_tts = settings.tts.xfyun
        if not (xfyun_tts.app_id and xfyun_tts.api_key and xfyun_tts.api_secret):
            sys.exit("未配置 tts.xfyun.app_id/api_key/api_secret，无法调用讯飞 TTS")
        tts = XfyunTTS(xfyun_tts, settings.tts)
        voice_label = xfyun_tts.voice
    else:
        sys.exit(f"未知 tts.provider: {settings.tts.provider}（可选 step / xfyun）")

    prompts = {
        "greeting.wav": settings.prompts.voice_assets.greeting,
        "wake.wav": settings.prompts.voice_assets.wake,
        "error.wav": settings.prompts.voice_assets.error,
        "sleep.wav": settings.prompts.voice_assets.sleep,
    }

    ASSETS_DIR.mkdir(exist_ok=True)
    try:
        for name, text in prompts.items():
            if not text:
                print(f"跳过 {name}：未配置 prompts.voice_assets 文案")
                continue
            path = ASSETS_DIR / name
            path.write_bytes(await tts.synthesize(text))
            print(f"生成 {path}（{settings.tts.provider}/{voice_label}）: {text}")
    finally:
        await tts.close()


def main(config_path: str | None):
    asyncio.run(generate(config_path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    main(args.config)
