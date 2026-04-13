"""AEC microphone source — wraps the native `aec_mic` Swift binary.

The binary runs Apple's VoiceProcessingIO (same AEC stack as FaceTime/Zoom)
and streams 16 kHz Int16 mono PCM to stdout. This module launches it as a
subprocess and exposes a blocking read API + an async iterator.

Typical usage (blocking):
    with AECMicStream() as mic:
        while True:
            chunk = mic.read(320)        # 320 samples = 20 ms
            if not chunk:
                break
            process(chunk)

Async usage:
    async for chunk in AECMicStream().frames(samples_per_chunk=320):
        await process(chunk)
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import AsyncIterator, Iterator

SAMPLE_RATE = 16_000
CHANNELS = 1
BYTES_PER_SAMPLE = 2  # Int16

# Resolved once: absolute path to the compiled aec_mic binary.
_BINARY_PATH = Path(__file__).resolve().parent.parent / "native_aec" / "aec_mic"


class AECMicError(RuntimeError):
    """Raised when the native AEC helper cannot be started or dies."""


class AECMicStream:
    """Read echo-cancelled 16 kHz Int16 mono PCM from the system mic.

    The Swift helper keeps running until `close()` is called or the process
    dies. Stderr lines from the helper are forwarded to this process's stderr
    prefixed with `[aec_mic]` so runtime issues remain visible.
    """

    def __init__(self, binary_path: Path | str | None = None) -> None:
        self._binary = Path(binary_path) if binary_path else _BINARY_PATH
        self._proc: subprocess.Popen[bytes] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._closed = False

    # ── Context manager ─────────────────────────────────────────────────

    def __enter__(self) -> "AECMicStream":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── Lifecycle ───────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the Swift helper. Idempotent."""
        if self._proc is not None:
            return
        if not self._binary.exists():
            raise AECMicError(
                f"aec_mic binary not found at {self._binary}. "
                f"Build with: swiftc -O native_aec/aec_mic.swift -o native_aec/aec_mic"
            )
        if not os.access(self._binary, os.X_OK):
            raise AECMicError(f"aec_mic at {self._binary} is not executable")

        self._proc = subprocess.Popen(
            [str(self._binary)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,  # unbuffered — we want samples as soon as they arrive
        )
        # Drain stderr in a background thread so the helper's pipe never blocks.
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True,
        )
        self._stderr_thread.start()

    def close(self) -> None:
        """Terminate the helper and clean up pipes."""
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        if proc is None:
            return
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1.0)
        except ProcessLookupError:
            pass
        finally:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()

    # ── Blocking read ────────────────────────────────────────────────────

    def read(self, samples: int) -> bytes:
        """Read exactly `samples` Int16 samples (blocks until available).

        Returns an empty bytes object on EOF (helper died).
        """
        if self._proc is None or self._proc.stdout is None:
            raise AECMicError("AECMicStream not started")
        need = samples * BYTES_PER_SAMPLE
        buf = bytearray()
        while len(buf) < need:
            chunk = self._proc.stdout.read(need - len(buf))
            if not chunk:
                return bytes(buf)  # partial or empty → EOF
            buf.extend(chunk)
        return bytes(buf)

    def frames(self, samples_per_chunk: int = 320) -> Iterator[bytes]:
        """Generator of fixed-size PCM chunks. Default 20 ms at 16 kHz."""
        while not self._closed:
            chunk = self.read(samples_per_chunk)
            if len(chunk) < samples_per_chunk * BYTES_PER_SAMPLE:
                return
            yield chunk

    # ── Async ────────────────────────────────────────────────────────────

    async def aframes(self, samples_per_chunk: int = 320) -> AsyncIterator[bytes]:
        """Async iterator — reads in a thread to avoid blocking the loop."""
        loop = asyncio.get_running_loop()
        while not self._closed:
            chunk = await loop.run_in_executor(None, self.read, samples_per_chunk)
            if not chunk or len(chunk) < samples_per_chunk * BYTES_PER_SAMPLE:
                return
            yield chunk

    # ── Health ───────────────────────────────────────────────────────────

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ── Internals ────────────────────────────────────────────────────────

    def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for raw in iter(proc.stderr.readline, b""):
            try:
                line = raw.decode("utf-8", errors="replace").rstrip()
            except Exception:
                continue
            if line:
                print(f"[aec_mic] {line}", file=sys.stderr, flush=True)


# ── Module-level convenience ─────────────────────────────────────────────

def build_instructions() -> str:
    return (
        "Swift AEC helper not built. Run:\n"
        "  swiftc -O native_aec/aec_mic.swift -o native_aec/aec_mic"
    )
