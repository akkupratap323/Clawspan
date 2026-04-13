"""Pipecat transport that uses the native Swift VoiceProcessingIO AEC helper
for microphone capture, while reusing Pipecat's `LocalAudioOutputTransport`
for speaker output.

The Swift binary (`native_aec/aec_mic`) delivers 16 kHz Int16 mono PCM with
Apple's echo cancellation applied, so the mic never hears the bot's TTS.

Usage:
    transport = AECAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_sample_rate=24000,
        )
    )

Fallback:
    If the Swift binary isn't built, falls back to `LocalAudioTransport`
    (PyAudio, no AEC) and logs a warning.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

from pipecat.frames.frames import InputAudioRawFrame, StartFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.local.audio import (
    LocalAudioOutputTransport,
    LocalAudioTransportParams,
)

try:
    import pyaudio
    _PYAUDIO_AVAILABLE = True
except ImportError:
    pyaudio = None  # type: ignore[assignment]
    _PYAUDIO_AVAILABLE = False

from tools.aec_mic import AECMicStream, SAMPLE_RATE as AEC_SAMPLE_RATE

# The Swift helper is hard-coded to 16 kHz mono Int16. Pipecat will honour
# whatever we declare here when building InputAudioRawFrame.
_AEC_CHANNELS = 1


class AECAudioInputTransport(BaseInputTransport):
    """Mic input driven by the native VoiceProcessingIO subprocess.

    A background thread reads fixed 20 ms PCM chunks from the Swift helper
    and schedules `push_audio_frame()` on the pipeline's event loop.
    """

    _params: LocalAudioTransportParams

    def __init__(self, params: LocalAudioTransportParams) -> None:
        super().__init__(params)
        self._mic: Optional[AECMicStream] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._sample_rate = AEC_SAMPLE_RATE

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)

        if self._mic is not None:
            return

        # Validate that downstream sample rate expectations match.
        requested = self._params.audio_in_sample_rate or frame.audio_in_sample_rate
        if requested and requested != AEC_SAMPLE_RATE:
            logger.warning(
                f"[AEC] pipeline requested {requested} Hz input but Swift helper "
                f"produces {AEC_SAMPLE_RATE} Hz. Using {AEC_SAMPLE_RATE} Hz; "
                f"downstream services must handle resampling."
            )

        try:
            self._mic = AECMicStream()
            self._mic.start()
        except Exception as e:
            logger.error(f"[AEC] failed to start native AEC helper: {e}")
            raise

        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="AECAudioReader",
            daemon=True,
        )
        self._reader_thread.start()

        logger.info(f"[AEC] input transport started at {AEC_SAMPLE_RATE} Hz mono")
        await self.set_transport_ready(frame)

    async def cleanup(self) -> None:
        await super().cleanup()
        self._stop_event.set()
        if self._mic is not None:
            try:
                self._mic.close()
            except Exception as e:
                logger.warning(f"[AEC] mic close error: {e}")
            self._mic = None
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.5)
            self._reader_thread = None

    # ── Reader ────────────────────────────────────────────────────────

    def _reader_loop(self) -> None:
        """Pull PCM chunks from the Swift helper and push frames to the loop."""
        # 20 ms at 16 kHz = 320 samples = 640 bytes. Matches Pipecat convention.
        samples_per_chunk = int(AEC_SAMPLE_RATE / 100) * 2  # 20 ms
        loop = self.get_event_loop()
        mic = self._mic
        if mic is None:
            return

        while not self._stop_event.is_set():
            try:
                chunk = mic.read(samples_per_chunk)
            except Exception as e:
                logger.error(f"[AEC] reader error: {e}")
                return
            if not chunk:
                logger.warning("[AEC] helper EOF — reader exiting")
                return
            if len(chunk) < samples_per_chunk * 2:
                # Partial read right before close — drop it.
                continue

            audio_frame = InputAudioRawFrame(
                audio=chunk,
                sample_rate=AEC_SAMPLE_RATE,
                num_channels=_AEC_CHANNELS,
            )
            try:
                asyncio.run_coroutine_threadsafe(
                    self.push_audio_frame(audio_frame), loop,
                )
            except RuntimeError:
                # Loop closed — stop.
                return


class AECAudioTransport(BaseTransport):
    """Bundles the native-AEC input + Pipecat's local PyAudio output.

    Drop-in replacement for `LocalAudioTransport` for microphone capture.
    Output playback continues through PyAudio since it does not need AEC.
    """

    def __init__(self, params: LocalAudioTransportParams) -> None:
        super().__init__()
        self._params = params
        if not _PYAUDIO_AVAILABLE:
            raise RuntimeError(
                "pyaudio missing — install pipecat-ai[local] + portaudio"
            )
        self._pyaudio = pyaudio.PyAudio()
        self._input: Optional[AECAudioInputTransport] = None
        self._output: Optional[LocalAudioOutputTransport] = None

    def input(self) -> FrameProcessor:
        if self._input is None:
            self._input = AECAudioInputTransport(self._params)
        return self._input

    def output(self) -> FrameProcessor:
        if self._output is None:
            self._output = LocalAudioOutputTransport(self._pyaudio, self._params)
        return self._output


# ── Factory with graceful fallback ────────────────────────────────────────

def build_audio_transport(params: LocalAudioTransportParams) -> BaseTransport:
    """Return AECAudioTransport if Swift helper exists, else LocalAudioTransport.

    Prints a clear warning if falling back, so users know AEC is off.
    """
    binary = Path(__file__).resolve().parent.parent / "native_aec" / "aec_mic"
    if binary.exists() and binary.is_file():
        logger.info(f"[AEC] using native VoiceProcessingIO helper at {binary}")
        return AECAudioTransport(params)

    from pipecat.transports.local.audio import LocalAudioTransport
    logger.warning(
        f"[AEC] Swift helper not found at {binary}. "
        f"Falling back to PyAudio (NO echo cancellation). "
        f"Build with: swiftc -O native_aec/aec_mic.swift -o native_aec/aec_mic"
    )
    return LocalAudioTransport(params)
