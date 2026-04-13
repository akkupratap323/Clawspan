"""
WakeWord — "Hey Clawspan" detection using OpenWakeWord (ONNX).
Uses sounddevice (not PyAudio) to avoid macOS volume ducking conflicts.
"""

import os
import queue
import numpy as np
import sounddevice as sd

WAKE_MODEL_PATH = os.path.join(os.path.dirname(__file__), "hey_jarvis.onnx")
SAMPLE_RATE     = 16000
CHUNK_SAMPLES   = 1280   # 80ms — openwakeword expects this size
THRESHOLD       = 0.5


class WakeWordDetector:
    def __init__(self, threshold: float = THRESHOLD):
        self._threshold = threshold
        self._model = None
        self._load_model()

    def _load_model(self) -> None:
        try:
            from openwakeword.model import Model
            self._model = Model(
                wakeword_models=[WAKE_MODEL_PATH],
                inference_framework="onnx",
            )
            print("[Wake] 'Hey Clawspan' detector ready.")
        except Exception as e:
            print(f"[Wake] OpenWakeWord load failed: {e}")

    def wait_for_wake_word(self) -> None:
        """Block until 'Hey Clawspan' is detected."""
        if self._model is None:
            print("[Wake] Model not loaded — skipping wake word, activating now.")
            return

        print("[Clawspan] Standing by... say 'Hey Clawspan' to activate.\n")

        q: queue.Queue = queue.Queue()

        def _callback(indata, frames, time, status):
            # Convert float32 → int16 for openwakeword
            pcm = (np.clip(indata[:, 0], -1.0, 1.0) * 32767).astype(np.int16)
            q.put(pcm)

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SAMPLES,
            callback=_callback,
            device=None,  # use system default input device
        ):
            while True:
                audio = q.get()
                self._model.predict(audio)
                scores = list(self._model.prediction_buffer.get("hey_jarvis", []))
                if scores and max(scores[-3:]) > self._threshold:
                    self._model.prediction_buffer["hey_jarvis"] = []
                    print("[Wake] 'Hey Clawspan' detected!")
                    break
