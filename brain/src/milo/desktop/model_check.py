"""An explicit, playback-free check of the models shipped in a desktop distribution."""
from __future__ import annotations

import json
import math
import time
import wave
from pathlib import Path

import numpy as np


def check_models(output: Path, audio: Path | None = None) -> int:
    from milo.adapters.embed.onnx_e5 import OnnxE5
    from milo.adapters.stt.faster_whisper import FasterWhisper
    from milo.adapters.tts.pocket import PocketTTS

    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {}
    started = time.monotonic()
    print("Checking semantic memory...", flush=True)
    memory = OnnxE5()
    passages = memory.embed(["My dentist appointment is tomorrow morning.",
                            "The server uses PostgreSQL databases.", "Ich besuche morgen früh den Zahnarzt."])
    scores = (memory.embed(["When is my dental visit?"], query=True) @ passages.T)[0].tolist()
    if not (scores[0] > scores[1] + .04 and scores[2] > scores[1] + .04):
        raise RuntimeError(f"Semantic memory check failed: {scores}")
    report["memory"] = {"scores": scores, "seconds": time.monotonic() - started}
    started = time.monotonic()
    print("Loading local speech recognition...", flush=True)
    recognizer = FasterWhisper(preview_model="")
    recognizer.warm()
    speech = {"load_seconds": time.monotonic() - started}
    if audio is not None:
        with wave.open(str(audio), "rb") as source:
            if source.getsampwidth() != 2 or source.getnchannels() not in (1, 2):
                raise ValueError("Model-check audio must be mono or stereo 16-bit PCM")
            rate, channels = source.getframerate(), source.getnchannels()
            if source.getnframes() > rate * 30:
                raise ValueError("Use at most 30 seconds of model-check audio")
            samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768
            samples = samples.reshape(-1, channels).mean(axis=1)
        if rate != 16000:
            from scipy.signal import resample_poly
            divisor = math.gcd(rate, 16000)
            samples = resample_poly(samples, 16000 // divisor, rate // divisor).astype(np.float32)
        started = time.monotonic()
        text = recognizer.transcribe(samples)
        words = recognizer.words(samples)
        if not text.strip() or not words or any(w.start < 0 or w.end < w.start for w in words):
            raise RuntimeError("Local speech recognition produced no valid timed transcript")
        speech.update(text=text, timed_words=len(words), seconds=time.monotonic() - started)
    report["speech"] = speech
    voice = PocketTTS()
    print("Checking English and German voice generation...", flush=True)
    report["voice"] = {}
    for language, text in (("english", "Milo is ready on this computer."),
                           ("german", "Milo ist bereit auf diesem Computer.")):
        started = time.monotonic()
        samples = voice.synthesize(text)
        if len(samples) < voice.sample_rate // 4 or not np.isfinite(samples).all() or np.max(np.abs(samples)) < .001:
            raise RuntimeError(f"The {language} voice produced no valid audio")
        with wave.open(str(output / (language + ".wav")), "wb") as target:
            target.setparams((1, 2, voice.sample_rate, 0, "NONE", "not compressed"))
            target.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
        report["voice"][language] = {"seconds": time.monotonic() - started,
                                     "audio_seconds": len(samples) / voice.sample_rate}
    (output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0
