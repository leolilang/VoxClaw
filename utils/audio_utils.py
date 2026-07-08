"""音频数据格式转换工具。

内部管线统一使用 float32 单声道 [-1, 1]；与外部交互时转换为 int16 / WAV。
"""

import io
import wave

import numpy as np


def float_to_int16(audio: np.ndarray) -> np.ndarray:
    clipped = np.clip(audio, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16)


def int16_to_float(audio: np.ndarray) -> np.ndarray:
    return audio.astype(np.float32) / 32768.0


def float_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    pcm = float_to_int16(audio)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def wav_bytes_to_float(data: bytes) -> tuple[np.ndarray, int]:
    """解码 WAV 字节流，返回 (float32 单声道音频, 采样率)。"""
    with wave.open(io.BytesIO(data), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if sampwidth == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sampwidth == 1:
        audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"不支持的采样位宽: {sampwidth * 8} bit")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, sample_rate


def duration_s(audio: np.ndarray, sample_rate: int) -> float:
    return len(audio) / sample_rate
