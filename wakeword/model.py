"""openWakeWord 模型加载。

支持两种方式：
1. 内置预训练模型名，如 "hey_jarvis"、"alexa"（首次运行会自动下载基础模型）
2. 放在 wakeword/hotwords/ 目录下的自训练 .onnx 模型，如 "hey_kiwi.onnx"
"""

from pathlib import Path

from loguru import logger
from openwakeword.model import Model

HOTWORDS_DIR = Path(__file__).resolve().parent / "hotwords"


def _ensure_base_models():
    """openWakeWord 依赖的 melspectrogram/embedding 基础模型，缺失时自动下载。"""
    import openwakeword
    from openwakeword.utils import download_models

    resources = Path(openwakeword.__file__).parent / "resources" / "models"
    mel = resources / "melspectrogram.onnx"
    if not mel.exists():
        logger.info("首次运行，下载 openWakeWord 基础模型...")
        download_models()


def load_wakeword_model(name: str) -> Model:
    _ensure_base_models()

    custom_path = HOTWORDS_DIR / name
    if custom_path.exists():
        model_ref = str(custom_path)
        logger.info("加载自训练唤醒词模型: {}", custom_path)
    else:
        model_ref = name.removesuffix(".onnx")
        logger.info("加载内置唤醒词模型: {}", model_ref)

    return Model(wakeword_models=[model_ref], inference_framework="onnx")
