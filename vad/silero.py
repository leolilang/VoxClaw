"""Silero VAD (v5)：直接用 onnxruntime 推理，无 torch 依赖。

模型文件来自 silero-vad pip 包内置的 silero_vad.onnx。
输入为 16kHz、512 采样点的 float32 块，输出语音概率。
"""

from pathlib import Path

import numpy as np
import onnxruntime as ort
from loguru import logger

SAMPLE_RATE = 16000
CHUNK_SIZE = 512
CONTEXT_SIZE = 64  # v5 模型要求在每块前拼接上一块末尾 64 个采样点


def _find_model_path() -> Path:
    import silero_vad

    pkg_dir = Path(silero_vad.__file__).parent
    for candidate in pkg_dir.rglob("silero_vad.onnx"):
        return candidate
    raise FileNotFoundError("在 silero-vad 包中找不到 silero_vad.onnx，请检查安装")


class SileroVAD:
    def __init__(self, threshold: float = 0.55):
        self.threshold = threshold
        model_path = _find_model_path()
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SIZE), dtype=np.float32)
        logger.info("Silero VAD 已加载: {}", model_path)

    def process(self, chunk: np.ndarray) -> float:
        """输入 float32 块（长度 512），返回语音概率 [0, 1]。"""
        chunk = np.asarray(chunk, dtype=np.float32).ravel()
        if len(chunk) != CHUNK_SIZE:
            raise ValueError(f"VAD 块大小必须为 {CHUNK_SIZE}，实际为 {len(chunk)}")

        x = np.concatenate([self._context, chunk[np.newaxis, :]], axis=1)
        out, self._state = self._session.run(
            ["output", "stateN"],
            {
                "input": x,
                "state": self._state,
                "sr": np.array(SAMPLE_RATE, dtype=np.int64),
            },
        )
        self._context = x[:, -CONTEXT_SIZE:]
        return float(out[0, 0])

    def is_speech(self, chunk: np.ndarray) -> bool:
        return self.process(chunk) >= self.threshold

    def reset(self):
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SIZE), dtype=np.float32)
