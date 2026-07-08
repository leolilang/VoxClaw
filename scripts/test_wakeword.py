"""唤醒词灵敏度实测：实时打印检测分数，用于调整 wakeword.threshold。

用法:
    python scripts/test_wakeword.py [--config config/config.yaml] [--seconds 30]

对麦克风说唤醒词（如 "Hey Jarvis"），观察输出分数：
- 分数经常超过阈值但没唤醒 -> 检查 cooldown
- 分数总在阈值之下 -> 调低 threshold（如 0.3）
- 完全没有分数波动 -> 检查麦克风输入设备/权限
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from audio.recorder import MicrophoneRecorder
from config.settings import load_settings
from utils.audio_utils import float_to_int16
from wakeword.detector import OWW_CHUNK
from wakeword.model import load_wakeword_model


async def main(config_path: str | None, seconds: float):
    settings = load_settings(config_path)
    model = load_wakeword_model(settings.wakeword.model)
    mic = MicrophoneRecorder(settings.audio)
    mic.start()
    threshold = settings.wakeword.threshold
    print(f"\n开始监听 {seconds:.0f}s，请对麦克风说唤醒词（当前阈值 {threshold}）...\n")

    pending = np.empty(0, dtype=np.int16)
    peak = 0.0
    elapsed = 0.0
    block_s = settings.audio.block_size / settings.audio.sample_rate
    try:
        while elapsed < seconds:
            frame = await mic.get_frame()
            elapsed += block_s
            rms = float(np.sqrt(np.mean(frame**2)))
            pending = np.concatenate([pending, float_to_int16(frame)])
            while len(pending) >= OWW_CHUNK:
                chunk, pending = pending[:OWW_CHUNK], pending[OWW_CHUNK:]
                score = max(model.predict(chunk).values())
                peak = max(peak, score)
                if score >= 0.05:
                    bar = "#" * int(score * 40)
                    mark = "  <== 超过阈值，会触发唤醒" if score >= threshold else ""
                    print(f"[{elapsed:5.1f}s] score={score:.3f} rms={rms:.4f} {bar}{mark}")
    finally:
        mic.stop()

    print(f"\n结束。本次最高分: {peak:.3f}（阈值 {threshold}）")
    if peak == 0.0:
        print("没有任何分数波动，请检查麦克风权限/输入设备（python -m audio.device）")
    elif peak < threshold:
        print(f"建议把 config.yaml 的 wakeword.threshold 调低到 {max(0.2, round(peak - 0.05, 2))} 左右")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--seconds", type=float, default=30.0)
    args = parser.parse_args()
    asyncio.run(main(args.config, args.seconds))
