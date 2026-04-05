"""Custom Pipecat mute strategies for echo prevention.

Pipecat ships `MuteUntilFirstBotCompleteUserMuteStrategy` which mutes the
user mic until the bot finishes its opening statement. We add a
`PostSpeechMuteStrategy` that mutes during every bot utterance plus a short
tail, so speaker audio bleeding into the mic is never re-transcribed.

This is JARVIS's production echo-cancellation approach — simpler and more
reliable than the native VPIO AEC path kept under native_aec/ for showcase.
"""

from __future__ import annotations

import time

from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame
from pipecat.turns.user_mute.base_user_mute_strategy import BaseUserMuteStrategy


class PostSpeechMuteStrategy(BaseUserMuteStrategy):
    """Mute the mic while the bot is speaking, plus a configurable tail.

    The tail covers the brief window after TTS completion where the tail of
    the audio buffer is still being emitted from the speaker — without it,
    the STT pipeline re-ingests the bot's own final syllables.
    """

    def __init__(self, post_speech_secs: float = 1.5) -> None:
        super().__init__()
        self._bot_speaking = False
        self._mute_until: float = 0.0
        self._post_speech_secs = post_speech_secs

    async def reset(self) -> None:
        self._bot_speaking = False
        self._mute_until = 0.0

    async def process_frame(self, frame) -> bool:
        await super().process_frame(frame)
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            self._mute_until = time.monotonic() + self._post_speech_secs
        return self._bot_speaking or time.monotonic() < self._mute_until
