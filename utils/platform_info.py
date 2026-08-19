"""跨平台运行环境日志。"""

import platform
import sys

import sounddevice as sd
from loguru import logger


def log_runtime_environment():
    """输出操作系统、Python 与音频后端信息，方便 macOS/Windows 排障。"""
    system = platform.system() or "Unknown"
    release = platform.release()
    machine = platform.machine()
    python = platform.python_version()
    logger.info("运行环境: {} {} ({}) / Python {}", system, release, machine, python)

    try:
        hostapis = sd.query_hostapis()
        api_names = [api.get("name", "unknown") for api in hostapis]
        logger.info("PortAudio 后端: {}", ", ".join(api_names) if api_names else "未发现")
    except Exception as exc:
        logger.warning("查询 PortAudio 后端失败: {}", exc)

    if system == "Darwin":
        logger.info("macOS 权限提示：首次运行需给终端授权麦克风；DEBUG 全局热键还需要辅助功能权限")
    elif system == "Windows":
        logger.info("Windows 权限提示：请确认 系统设置 -> 隐私和安全性 -> 麦克风 已允许桌面应用访问")
    else:
        logger.warning("当前系统 {} 未作为主要支持平台测试，音频设备和热键可能需要额外适配", sys.platform)
