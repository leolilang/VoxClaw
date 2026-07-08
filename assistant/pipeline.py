"""语音助手主管线：唤醒 -> 录音 -> STT -> LLM -> TTS -> 播放。

支持单轮/多轮对话（conversation.mode），多轮时答完继续监听追问。
"""

import asyncio
from pathlib import Path

from loguru import logger

from assistant.session import Session
from assistant.state_machine import State, StateMachine
from audio.player import AudioPlayer
from audio.recorder import MicrophoneRecorder
from config.settings import Settings
from llm.openclaw import OpenClawClient
from stt.step_stt import StepSTT
from tts.step_tts import StepTTS
from tts.step_tts_ws import StepTTSWebSocket
from utils.timer import Timer
from utils.text_utils import clean_for_tts, is_exit_command
from vad.recorder import VADRecorder
from wakeword.detector import WakeWordDetector

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


class VoicePipeline:
    def __init__(
        self,
        settings: Settings,
        mic: MicrophoneRecorder,
        player: AudioPlayer,
        wakeword: WakeWordDetector,
        vad_recorder: VADRecorder,
        stt: StepSTT,
        llm: OpenClawClient,
        tts: StepTTS,
        tts_ws: StepTTSWebSocket | None = None,
    ):
        self._settings = settings
        self._mic = mic
        self._player = player
        self._wakeword = wakeword
        self._vad_recorder = vad_recorder
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._tts_ws = tts_ws
        self._state = StateMachine()
        self._session = Session()
        self._running = False

    async def run(self):
        self._running = True
        self._mic.start()
        conv = self._settings.conversation
        logger.info(
            "VoxClaw 已就绪（{}对话模式），等待唤醒词...",
            "多轮" if conv.mode == "multi" else "单轮",
        )
        await self._play_asset("greeting.wav")
        self._mic.clear()  # 丢弃问候语播放期间采集的回声
        try:
            while self._running:
                await self._wait_for_wakeword()
                if not self._running:
                    break
                try:
                    await self._conversation()
                except Exception:
                    logger.exception("对话处理失败")
                    await self._play_asset("error.wav")
                finally:
                    self._back_to_idle()
        finally:
            self._mic.stop()

    async def _wait_for_wakeword(self):
        while self._running:
            frame = await self._mic.get_frame()
            if self._wakeword.process(frame):
                return

    async def _conversation(self):
        """一次完整会话：唤醒后循环「录音 -> 回答」，直到单轮结束或追问超时。"""
        conv = self._settings.conversation
        follow_up = False
        while self._running:
            self._state.to_idle()
            self._state.transition(State.LISTENING)
            self._wakeword.reset()
            if not follow_up:
                await self._play_asset("wake.wav")  # 仅首次唤醒应答，追问时不重复播报
            self._mic.clear()  # 丢弃提示音/上一轮回复播放期间采集的回声

            timeout = conv.follow_up_timeout_s if follow_up else None
            audio = await self._vad_recorder.record(self._mic, timeout_s=timeout)
            if audio is None:
                if follow_up:
                    logger.info("等待追问超时（{:.0f}s），结束多轮对话", conv.follow_up_timeout_s)
                return
            self._state.transition(State.RECORDING)

            try:
                exit_requested = await self._respond(audio)
            except Exception:
                logger.exception("本轮回答失败，保持对话等待重说")
                self._player.stop()
                await self._play_asset("error.wav")
                follow_up = True  # 出错不退出会话，等待用户重新提问，直到超时或退出指令
                continue
            if exit_requested:
                logger.info("收到退出指令，结束对话")
                return

            if conv.mode != "multi":
                return
            follow_up = True
            logger.info("多轮模式：{:.0f}s 内可直接追问（无需唤醒词）", conv.follow_up_timeout_s)

    async def _respond(self, audio) -> bool:
        """执行 STT -> LLM -> TTS -> 播放；用户说了退出指令时返回 True。"""
        turn = Timer()
        self._state.transition(State.THINKING)

        text = await self._stt.transcribe(audio, self._settings.audio.sample_rate)
        if not text:
            logger.info("未识别到有效文本")
            await self._play_asset("error.wav")
            return False

        if is_exit_command(text, self._settings.conversation.exit_words):
            logger.info("识别到退出指令: {!r}", text)
            await self._play_asset("sleep.wav")
            return True

        asyncio.ensure_future(self._play_asset("thinking.wav"))
        reply = await self._llm.chat(self._session, text)
        speech_text = clean_for_tts(reply) if reply else ""
        if not speech_text:
            await self._play_asset("error.wav")
            return False

        self._state.transition(State.SPEAKING)
        if self._tts_ws is not None:
            # 流式：边合成边播放，首句合成完即出声
            await self._player.play_pcm_stream(
                self._tts_ws.stream(speech_text), self._tts_ws.sample_rate
            )
        else:
            wav = await self._tts.synthesize(speech_text)
            await self._player.play_wav_bytes(wav)
        logger.info("本轮对话完成，总耗时 {:.1f}s", turn.elapsed_ms() / 1000)
        return False

    def _back_to_idle(self):
        self._state.to_idle()
        self._mic.clear()  # 丢弃播放期间采集的回声
        self._wakeword.reset()
        logger.info("返回待机，等待唤醒词...")

    async def _play_asset(self, name: str):
        await self._player.play_file(ASSETS_DIR / name)

    async def shutdown(self):
        self._running = False
        self._player.stop()
        await asyncio.gather(
            self._stt.close(), self._llm.close(), self._tts.close(),
            return_exceptions=True,
        )
