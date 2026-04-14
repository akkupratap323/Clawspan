"""Voice passphrase gate that runs at pipeline startup.

Two entry points for existing vs first-run users, gated by
`core.auth.is_setup()`. The gate captures microphone audio via sounddevice,
ships it to Deepgram's prerecorded endpoint for transcription, then matches
against the stored passphrase hash.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import wave

import requests

from config import DEEPGRAM_API_KEY
from core.auth import check, is_setup, lockout_remaining, setup_password
from utils import play_sound


def _listen_and_transcribe(timeout_secs: float = 10.0, sample_rate: int = 16000) -> str:
    """Record from the default mic until silence, transcribe via Deepgram.

    Returns the transcribed text (stripped), or an empty string when no
    speech was captured or the API call failed. Kept synchronous so it can
    be offloaded via ``asyncio.to_thread``.
    """
    import numpy as np
    import sounddevice as sd

    print("[Auth] Listening... speak your passphrase now.", flush=True)
    frames: list = []
    speech_started = False
    silence_start: float | None = None
    silence_threshold = 0.002
    silence_duration = 1.5
    min_speech_secs = 0.2
    speech_start_time: float | None = None
    block_size = 512
    start_time = time.time()

    def callback(indata, frames_count, time_info, status) -> None:
        nonlocal speech_started, silence_start, speech_start_time
        if time.time() - start_time > timeout_secs:
            raise sd.CallbackStop()
        rms = float(np.sqrt(np.mean(indata ** 2)))
        if int(time.time() * 1000) % 2000 < 100:
            print(f"[Auth] Audio level: {rms:.5f} (threshold: {silence_threshold})", flush=True)
        if rms > silence_threshold:
            if not speech_started:
                speech_started = True
                speech_start_time = time.time()
                silence_start = None
                print(f"[Auth] Speech detected! (RMS={rms:.4f})", flush=True)
            else:
                silence_start = None
            frames.append(indata.copy())
        elif speech_started:
            if silence_start is None:
                silence_start = time.time()
            frames.append(indata.copy())
            if time.time() - silence_start > silence_duration:
                if speech_start_time and (silence_start - speech_start_time) > min_speech_secs:
                    print(f"[Auth] Speech ended after {time.time() - speech_start_time:.1f}s", flush=True)
                    raise sd.CallbackStop()

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        callback=callback,
        blocksize=block_size,
    ):
        try:
            sd.sleep(int(timeout_secs * 1000))
        except sd.CallbackStop:
            pass

    if not frames:
        print("[Auth] No audio captured.", flush=True)
        return ""

    audio = np.concatenate(frames, axis=0).flatten()
    print(f"[Auth] Captured {len(audio)} samples ({len(audio) / sample_rate:.1f}s)", flush=True)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        audio_bytes = (audio * 32767).astype(np.int16).tobytes()
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)

        with open(tmp_path, "rb") as f:
            resp = requests.post(
                "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&language=en",
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "audio/wav",
                },
                data=f.read(),
                timeout=15,
            )
        data = resp.json()
        text = (
            data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
            .get("transcript", "")
        )
        return text.strip()
    except Exception as e:
        print(f"[Auth] Transcription error: {e}", flush=True)
        return ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _verify_existing_user() -> bool:
    """Give the user 3 attempts to speak their passphrase. Returns True on success."""
    print("\n[Auth] Access verification required.", flush=True)
    print("[Auth] Speak your passphrase, sir.", flush=True)

    for attempt in range(3):
        remaining = lockout_remaining()
        if remaining > 0:
            print(f"[Auth] Account locked. Try again in {remaining}s.", flush=True)
            await asyncio.sleep(remaining)
            continue

        heard = await asyncio.to_thread(_listen_and_transcribe, timeout_secs=10.0)
        if not heard:
            print("[Auth] No speech detected. Try again.", flush=True)
            play_sound("error")
            continue

        print(f"[Auth] Heard: '{heard}'", flush=True)
        result = check(heard)

        if result == "ok":
            print("[Auth] Identity confirmed. Welcome back, sir.", flush=True)
            play_sound("success")
            return True
        if result == "locked":
            remaining = lockout_remaining()
            print(f"[Auth] Access denied. Locked for {remaining}s.", flush=True)
            play_sound("error")
            return False

        attempts_left = 2 - attempt
        print(f"[Auth] Wrong passphrase. {attempts_left} attempts left.", flush=True)
        play_sound("error")

    print("[Auth] All attempts exhausted. Goodbye.", flush=True)
    play_sound("error")
    return False


async def _first_time_setup() -> None:
    """Walk a new user through voice passphrase enrollment (best-effort)."""
    print("\n[Auth] First-time setup.", flush=True)
    print("[Auth] Speak a passphrase you'll remember — e.g. 'iron man mark fifty'.", flush=True)
    await asyncio.sleep(1.0)

    pw1 = await asyncio.to_thread(_listen_and_transcribe, timeout_secs=12.0)
    if not pw1:
        print("[Auth] No speech detected. Skipping passphrase setup.", flush=True)
        return

    print(f"[Auth] Heard: '{pw1}'", flush=True)
    await asyncio.sleep(0.5)
    print("[Auth] Say it again to confirm.", flush=True)
    pw2 = await asyncio.to_thread(_listen_and_transcribe, timeout_secs=12.0)
    if not pw2:
        print("[Auth] No speech detected. Skipping passphrase setup.", flush=True)
        return

    print(f"[Auth] Heard: '{pw2}'", flush=True)
    if pw1.strip().lower() == pw2.strip().lower():
        setup_password(pw1)
        print("[Auth] Passphrase set. Systems online.", flush=True)
        play_sound("success")
    else:
        print("[Auth] Didn't match. Skipping passphrase setup.", flush=True)


async def run_voice_auth_gate() -> bool:
    """Run the passphrase gate via voice (mic capture + STT). Returns True to continue."""
    if is_setup():
        return await _verify_existing_user()

    await _first_time_setup()
    return True


async def run_text_auth_gate() -> bool:
    """Run the passphrase gate via typed password input. Returns True to continue."""
    if is_setup():
        print("\n[Auth] Enter password:", flush=True)
        for attempt in range(3):
            remaining = lockout_remaining()
            if remaining > 0:
                print(f"[Auth] Locked. Wait {remaining}s.", flush=True)
                import asyncio
                await asyncio.sleep(remaining)
                continue

            pw = input("> ").strip()
            result = check(pw)

            if result == "ok":
                print("[Auth] Access granted.", flush=True)
                return True
            elif result == "locked":
                remaining = lockout_remaining()
                print(f"[Auth] Access denied. Locked for {remaining}s.", flush=True)
                return False
            else:
                attempts_left = 2 - attempt
                print(f"[Auth] Wrong password. {attempts_left} attempts left.", flush=True)

        print("[Auth] All attempts exhausted. Goodbye.", flush=True)
        return False

    # First run — set password
    print("\n[Auth] First-time setup.", flush=True)
    print("[Auth] Enter a password (will not be echoed):", flush=True)
    try:
        pw1 = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[Auth] Cancelled.", flush=True)
        return False

    if not pw1:
        print("[Auth] No password entered. Skipping setup.", flush=True)
        return True

    print("[Auth] Confirm password:", flush=True)
    try:
        pw2 = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[Auth] Cancelled.", flush=True)
        return False

    if pw1 == pw2:
        setup_password(pw1)
        print("[Auth] Password set. Systems online.", flush=True)
        return True

    print("[Auth] Passwords didn't match. Run again to set a password.", flush=True)
    return False
