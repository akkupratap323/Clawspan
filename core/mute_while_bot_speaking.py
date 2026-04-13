"""Mute user while bot speaks — eliminates speaker echo feedback loop.

Problem: Bot speaks → Mac speakers → built-in mic picks it up → VAD detects
as user speech → triggers false interruption → bot responds to its own echo.

Solution: Mute user during bot speech + brief echo tail after bot stops.
"""

from __future__ import annotations

import asyncio

from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame, Frame
from pipecat.turns.user_mute.base_user_mute_strategy import BaseUserMuteStrategy


class MuteWhileBotSpeakingUserMuteStrategy(BaseUserMuteStrategy):
    """Mutes user while bot is speaking, plus a short echo tail after."""

    def __init__(self, echo_tail_secs: float = 0.4):
        """
        Args:
            echo_tail_secs: Keep user muted this many seconds after bot stops
                speaking, to catch residual speaker echo in the mic.
        """
        super().__init__()
        self._bot_speaking = False
        self._echo_tail_secs = echo_tail_secs

    async def reset(self):
        self._bot_speaking = False

    async def process_frame(self, frame: Frame) -> bool:
        """Return True = mute user, False = let user through."""
        await super().process_frame(frame)

        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            # Keep muted briefly after bot stops — catches residual echo
            async def _unmute_after_tail():
                await asyncio.sleep(self._echo_tail_secs)
                self._bot_speaking = False
            asyncio.ensure_future(_unmute_after_tail())

        return self._bot_speaking
