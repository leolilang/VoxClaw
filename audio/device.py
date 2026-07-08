"""音频设备管理：枚举与选择输入/输出设备。

命令行查看设备列表：python -m audio.device
"""

import sounddevice as sd
from loguru import logger


def list_devices() -> list[dict]:
    return list(sd.query_devices())


def input_devices() -> list[dict]:
    return [d for d in list_devices() if d["max_input_channels"] > 0]


def output_devices() -> list[dict]:
    return [d for d in list_devices() if d["max_output_channels"] > 0]


def resolve_device(device: int | str | None, kind: str) -> int | str | None:
    """校验设备是否存在，返回可传给 sounddevice 的设备标识。"""
    if device is None:
        return None
    try:
        info = sd.query_devices(device, kind=kind)
        logger.info("使用{}设备: {}", "输入" if kind == "input" else "输出", info["name"])
        return device
    except (ValueError, sd.PortAudioError):
        logger.warning("找不到{}设备 {!r}，回退到系统默认", kind, device)
        return None


def log_default_devices():
    try:
        in_dev = sd.query_devices(kind="input")
        out_dev = sd.query_devices(kind="output")
        logger.info("默认输入设备: {}", in_dev["name"])
        logger.info("默认输出设备: {}", out_dev["name"])
    except (ValueError, sd.PortAudioError) as e:
        logger.warning("查询默认音频设备失败: {}", e)


if __name__ == "__main__":
    print(sd.query_devices())
