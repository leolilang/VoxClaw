"""固定容量环形缓冲区，用于保留最近一段音频（如说话前的 pre-roll）。"""

import numpy as np


class RingBuffer:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity 必须为正整数")
        self._capacity = capacity
        self._buf = np.zeros(capacity, dtype=np.float32)
        self._pos = 0
        self._size = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return self._size

    def write(self, data: np.ndarray):
        data = np.asarray(data, dtype=np.float32).ravel()
        n = len(data)
        if n == 0:
            return
        if n >= self._capacity:
            self._buf[:] = data[-self._capacity:]
            self._pos = 0
            self._size = self._capacity
            return

        end = self._pos + n
        if end <= self._capacity:
            self._buf[self._pos:end] = data
        else:
            first = self._capacity - self._pos
            self._buf[self._pos:] = data[:first]
            self._buf[: end - self._capacity] = data[first:]
        self._pos = end % self._capacity
        self._size = min(self._size + n, self._capacity)

    def read_all(self) -> np.ndarray:
        """按时间顺序（旧 -> 新）返回缓冲区内全部数据的拷贝。"""
        if self._size < self._capacity:
            return self._buf[: self._size].copy()
        return np.concatenate([self._buf[self._pos:], self._buf[: self._pos]])

    def clear(self):
        self._pos = 0
        self._size = 0
