"""用 Step TTS 生成语音提示音（使用 config.yaml 中的音色与文案）。

生成:
    assets/greeting.wav  启动问候
    assets/wake.wav      唤醒应答
    assets/error.wav     识别失败
    assets/sleep.wav     退出应答

用法: python scripts/generate_voice_assets.py [--config config/config.yaml]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from config.settings import load_settings

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def main(config_path: str | None):
    settings = load_settings(config_path)
    if not settings.step.api_key:
        sys.exit("未配置 step.api_key，无法调用 TTS")
    prompts = {
        "greeting.wav": settings.prompts.voice_assets.greeting,
        "wake.wav": settings.prompts.voice_assets.wake,
        "error.wav": settings.prompts.voice_assets.error,
        "sleep.wav": settings.prompts.voice_assets.sleep,
    }

    ASSETS_DIR.mkdir(exist_ok=True)
    with httpx.Client(timeout=60.0) as client:
        for name, text in prompts.items():
            if not text:
                print(f"跳过 {name}：未配置 prompts.voice_assets 文案")
                continue
            resp = client.post(
                settings.step.tts_endpoint,
                headers={"Authorization": f"Bearer {settings.step.api_key}"},
                json={
                    "model": settings.step.tts_model,
                    "input": text,
                    "voice": settings.tts.voice,
                    "response_format": "wav",
                    "speed": settings.tts.speed,
                },
            )
            resp.raise_for_status()
            path = ASSETS_DIR / name
            path.write_bytes(resp.content)
            print(f"生成 {path}（{settings.tts.voice}）: {text}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    main(args.config)
