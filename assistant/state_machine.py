"""系统状态机：IDLE -> LISTENING -> RECORDING -> THINKING -> SPEAKING -> IDLE。"""

from enum import Enum

from loguru import logger


class State(Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    RECORDING = "RECORDING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"


TRANSITIONS: dict[State, set[State]] = {
    State.IDLE: {State.LISTENING},
    State.LISTENING: {State.RECORDING, State.IDLE},
    State.RECORDING: {State.THINKING, State.IDLE},
    State.THINKING: {State.SPEAKING, State.IDLE},
    State.SPEAKING: {State.IDLE},
}


class StateMachine:
    def __init__(self):
        self._state = State.IDLE

    @property
    def state(self) -> State:
        return self._state

    def transition(self, to: State):
        if to not in TRANSITIONS[self._state]:
            raise ValueError(f"非法状态转移: {self._state.value} -> {to.value}")
        logger.debug("状态: {} -> {}", self._state.value, to.value)
        self._state = to

    def to_idle(self):
        """从任意状态回到 IDLE。"""
        if self._state is not State.IDLE:
            logger.debug("状态: {} -> IDLE", self._state.value)
            self._state = State.IDLE
