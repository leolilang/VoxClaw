"""耗时统计工具。"""

import time
from contextlib import contextmanager

from loguru import logger


class Timer:
    def __init__(self):
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000

    def reset(self):
        self._start = time.perf_counter()


@contextmanager
def timed(name: str):
    """with timed("STT"): ...  结束后打印耗时。"""
    t = Timer()
    try:
        yield t
    finally:
        logger.debug("{} 耗时 {:.0f} ms", name, t.elapsed_ms())
