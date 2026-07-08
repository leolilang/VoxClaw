"""生成提示音资源（纯正弦波，无第三方依赖，无需 API Key）。

语音版提示音（greeting/wake/error/sleep，真人音色）请用 scripts/generate_voice_assets.py 生成；
本脚本只在对应文件不存在时写入音效版兜底，thinking.wav 始终重新生成。

用法: python scripts/generate_assets.py
"""

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 24000
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def tone(freq: float, duration_s: float, volume: float = 0.4) -> list[float]:
    n = int(SAMPLE_RATE * duration_s)
    fade = int(SAMPLE_RATE * 0.01)
    samples = []
    for i in range(n):
        v = volume * math.sin(2 * math.pi * freq * i / SAMPLE_RATE)
        if i < fade:
            v *= i / fade
        elif i > n - fade:
            v *= (n - i) / fade
        samples.append(v)
    return samples


def silence(duration_s: float) -> list[float]:
    return [0.0] * int(SAMPLE_RATE * duration_s)


def write_wav(path: Path, samples: list[float]):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples
        )
        wf.writeframes(frames)
    print(f"生成 {path}")


def main():
    ASSETS_DIR.mkdir(exist_ok=True)
    # 思考音：短促单音（始终生成）
    write_wav(ASSETS_DIR / "thinking.wav", tone(520, 0.08, 0.25))

    # 以下为音效版兜底，语音版存在时不覆盖
    fallbacks = {
        "wake.wav": tone(660, 0.12) + tone(880, 0.15),                     # 唤醒：上行双音
        "error.wav": tone(440, 0.15) + silence(0.05) + tone(330, 0.2),     # 错误：下行双音
        "sleep.wav": tone(880, 0.12, 0.3) + tone(660, 0.18, 0.3),          # 休眠：下行双音
        "greeting.wav": tone(660, 0.12) + tone(880, 0.12) + tone(990, 0.15),  # 启动：上行三音
    }
    for name, samples in fallbacks.items():
        path = ASSETS_DIR / name
        if path.exists():
            print(f"跳过 {path}（已存在，可能是语音版）")
        else:
            write_wav(path, samples)


if __name__ == "__main__":
    main()
