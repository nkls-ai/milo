"""End-to-end dictation: recorded speech played into a real brain, timed and checked word by word.

    scripts/e2e-dictation.sh                 # real Whisper on `say` voices (takes the model lock)
    scripts/e2e-dictation.sh --fake          # tone "speech" and the tone transcriber: no models, seconds

Each case is a dictation script with pauses, soft trailing words and room noise. It becomes a 16 kHz
recording: macOS `say` rendered to a file (nothing plays), or with --fake, tones that `[stt] use = "tones"`
hears. A brain on a throwaway workspace in /tmp hears it through the WAV microphone in real time. The runner
holds the key the way the app does (listen_start tentative at key-down, listen_confirm when the app shows
the recording, listen_stop at the end) and records what comes back over the socket: when the state showed, every
partial, the pasted text and when it came.

Each case runs with stream = "preview" and, to compare, "off" (with --fake, "off" is the tone transcriber on
the whole recording, which is what the brain would do). A run fails if dictation lost words that "off" got,
or if pasting, live words or the listening state were slower than the limits below. Nothing touches ~/Milo.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np

from milo.adapters.audio.wav_file import read_wav, write_wav
from milo.adapters.stt.tones import ToneCodec
from milo.core.types import STT_SAMPLE_RATE

from .runner import _connect, _stop

SR = STT_SAMPLE_RATE
LEAD_S = 0.3  # silence before the first word
SHOW_AFTER_S = 0.08  # the app confirms a press this long after key-down (PushToTalk.showAfter)
MODEL_LOCK = Path("/tmp/milo-models.lock")
VOICES = {"en": "Samantha", "de": "Anna"}
SPEECH_LEVEL = 0.6  # `say` renders near full scale; a close microphone hears less
TONE_LEVEL = 0.08


@dataclass(frozen=True)
class Part:
    text: str
    pause_s: float = 0.0  # silence after it
    level: float = 1.0  # loudness against the rest: 0.15 is trailing off softly


@dataclass(frozen=True)
class Case:
    id: str
    lang: str
    parts: tuple[Part, ...]
    release_s: float = 0.3  # the key is let go this long after the last word
    mic: float = 1.0  # the whole recording's level: 0.15 is a microphone far away
    noise: float = 0.002  # room noise, RMS
    voice: str = ""
    again: tuple[Part, ...] = ()  # a second dictation, the key pressed again `again_after_s` after the release
    again_after_s: float = 0.2
    streams: tuple[str, ...] = ()  # run these too, whatever the run's streams

    @property
    def script(self) -> str:
        return " ".join(p.text for p in self.parts + self.again)

    @property
    def takes(self) -> list[Case]:
        """One case per key press. The second begins speaking right away: the user goes on."""
        second = [replace(self, id=f"{self.id}-again", parts=self.again, again=(), lead_s=0.05)] if self.again else []
        return [replace(self, again=())] + second

    lead_s: float = LEAD_S  # silence before the first word


@dataclass(frozen=True)
class Limits:
    paste_s: float  # release to paste, dictations up to 20 s
    paste_long_s: float  # longer ones
    first_partial_s: float  # first live words after speech began
    state_s: float  # key-down to the listening state
    extra_lost: int  # words a case may miss beyond what "off" missed


REAL = Limits(paste_s=0.5, paste_long_s=1.0, first_partial_s=1.5, state_s=0.1, extra_lost=1)
FAKE = Limits(paste_s=0.3, paste_long_s=0.4, first_partial_s=1.0, state_s=0.1, extra_lost=0)

CASES = (
    Case("en-2s", "en", (Part("Sounds good, see you at the station."),)),
    Case("de-2s", "de", (Part("Klingt gut, bis morgen am Bahnhof."),)),
    Case("en-release-after-pause", "en", (
        Part("Can you send me the slides from the meeting", 0.6),
        Part("and the notes as well"),
    ), release_s=0.05),
    Case("de-soft-tail", "de", (
        Part("Ich brauche noch die Zahlen", 0.5),
        Part("für den Bericht am Freitag", level=0.1),
    ), release_s=0.15),
    Case("en-again-200ms", "en", (
        Part("Please book a table for four people", 0.4),
        Part("at the Italian place on Friday"),
    ), release_s=0.1, again=(Part("and ask them whether they have a quiet corner"),), streams=("off",)),
    Case("en-15s", "en", (
        Part("So I was thinking about the trip next week,", 0.8),
        Part("and honestly I would rather take the train", 0.5),
        Part("because the flight leaves far too early in the morning", 1.0),
        Part("and I really hate getting up before sunrise.", 0.6),
        Part("Maybe we can talk about it tonight", level=0.1),
    ), release_s=0.4),
    Case("de-15s", "de", (
        Part("Hallo Thomas, ich wollte nur kurz Bescheid geben.", 0.9),
        Part("Das Treffen morgen verschiebt sich auf den Nachmittag,", 0.5),
        Part("weil der Raum am Vormittag belegt ist.", 1.0),
        Part("Bring bitte die Unterlagen vom letzten Projekt mit", 0.4),
        Part("und sag Maria Bescheid", level=0.1),
    ), release_s=0.3),
    Case("en-15s-quiet-mic", "en", (
        Part("I looked at the draft this morning", 0.7),
        Part("and I think the second section needs a few more examples,", 0.5),
        Part("especially for the budget.", 1.1),
        Part("Could we talk about it on Thursday after lunch?"),
    ), mic=0.1, noise=0.0015, release_s=0.3),
    Case("en-60s", "en", (
        Part("Okay, so here is my plan for the weekend.", 0.9),
        Part("On Saturday morning I want to go to the farmers market and buy vegetables for the whole week,", 0.4),
        Part("then clean the kitchen and finally fix the shelf in the hallway that has been loose since March.", 1.2),
        Part("In the afternoon my sister is coming over with her kids, so we need snacks, juice and maybe a "
             "board game that works for the little ones.", 1.0),
        Part("Sunday is for the tax return.", 0.8),
        Part("I still need the receipts from the dentist, the invoice from the electrician and the letter from "
             "the bank about the interest on my savings account,", 0.5),
        Part("which I think is somewhere in the blue folder on my desk", 0.6),
        Part("or maybe in the drawer under the printer.", 1.3),
        Part("If there is time left I would like to call my grandmother, she has her birthday next week and I "
             "still have not decided what to give her.", 0.9),
        Part("Maybe a photo book with pictures from the summer.", 0.7),
        Part("Remind me to order it by Wednesday at the latest,", 0.4),
        Part("otherwise it will not arrive in time", level=0.1),
    ), voice="Daniel"),
    Case("de-60s", "de", (
        Part("Also, hier ist mein Plan für das Wochenende.", 0.9),
        Part("Am Samstag will ich morgens auf den Markt gehen und Gemüse für die ganze Woche kaufen,", 0.5),
        Part("danach die Küche putzen und endlich das Regal im Flur reparieren, das schon seit Wochen wackelt.", 1.1),
        Part("Am Nachmittag kommt meine Schwester mit den Kindern vorbei,", 0.4),
        Part("also brauchen wir Kekse, Saft und vielleicht ein Spiel, das auch die Kleinen verstehen.", 1.0),
        Part("Der Sonntag ist für die Steuererklärung.", 0.8),
        Part("Ich brauche noch die Rechnung vom Zahnarzt, die Quittung vom Elektriker und den Brief von der "
             "Bank,", 0.5),
        Part("der irgendwo in der blauen Mappe auf meinem Schreibtisch liegt", 0.6),
        Part("oder vielleicht in der Schublade unter dem Drucker.", 1.2),
        Part("Wenn noch Zeit bleibt, möchte ich meine Großmutter anrufen,", 0.4),
        Part("sie hat nächste Woche Geburtstag und ich weiß noch nicht, was ich ihr schenken soll.", 0.9),
        Part("Vielleicht ein Fotobuch mit Bildern vom Sommer.", 0.6),
        Part("Erinnere mich daran, es bis Mittwoch zu bestellen", level=0.1),
    )),
)

GATE = ("en-2s", "en-release-after-pause", "de-soft-tail", "en-15s-quiet-mic", "en-again-200ms")
"""The cases pytest runs with --fake on every gate: short, and each one a way words were lost before."""


# ---- words


def words(text: str) -> list[str]:
    text = text.lower().replace("-", " ")
    return re.sub(r"[^\w\s']", " ", text).split()


def align(ref: list[str], hyp: list[str]) -> tuple[int, int, int]:
    """Substitutions, deletions (words missing) and insertions turning `ref` into `hyp`."""
    rows = [(j, 0, 0, j) for j in range(len(hyp) + 1)]  # (cost, subs, dels, ins)
    for i in range(1, len(ref) + 1):
        prev, rows = rows, [(i, 0, i, 0)]
        for j in range(1, len(hyp) + 1):
            same = ref[i - 1] == hyp[j - 1]
            options = [
                (prev[j - 1][0] + (not same), prev[j - 1][1] + (not same), prev[j - 1][2], prev[j - 1][3]),
                (prev[j][0] + 1, prev[j][1], prev[j][2] + 1, prev[j][3]),
                (rows[j - 1][0] + 1, rows[j - 1][1], rows[j - 1][2], rows[j - 1][3] + 1),
            ]
            rows.append(min(options))
    _, subs, dels, ins = rows[-1]
    return subs, dels, ins


# ---- recordings


def vocabulary(cases: tuple[Case, ...] = CASES) -> list[str]:
    return sorted({w for case in cases for w in words(case.script)})


def recording(case: Case, *, fake: bool, cache: Path, codec: ToneCodec | None = None) -> np.ndarray:
    """The case as a 16 kHz recording, from `cache` when it was made before."""
    key = hashlib.sha1(json.dumps([asdict(case), fake, SPEECH_LEVEL, TONE_LEVEL]).encode()).hexdigest()[:12]
    path = cache / f"{case.id}-{'tones' if fake else 'say'}-{key}.wav"
    if path.exists():
        return read_wav(path)[0]
    rng = np.random.default_rng(int(key, 16) % 2**32)
    chunks = [np.zeros(int(case.lead_s * SR), dtype=np.float32)]
    with tempfile.TemporaryDirectory() as tmp:
        for part in case.parts:
            if fake:
                speech = codec.speak(" ".join(words(part.text)), TONE_LEVEL)
            else:
                speech = _say(case.voice or VOICES[case.lang], part.text, Path(tmp)) * SPEECH_LEVEL
            chunks += [speech * part.level, np.zeros(int(part.pause_s * SR), dtype=np.float32)]
    chunks.append(np.zeros(int(case.release_s * SR), dtype=np.float32))
    audio = np.concatenate(chunks) * case.mic
    audio = (audio + rng.normal(0, case.noise, len(audio))).astype(np.float32)
    cache.mkdir(parents=True, exist_ok=True)
    write_wav(path, audio, SR)
    return audio


def _say(voice: str, text: str, tmp: Path) -> np.ndarray:
    """`text` spoken by macOS into a file (never the speakers), trimmed of the silence `say` adds."""
    aiff, wav = tmp / "part.aiff", tmp / "part.wav"
    subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", f"LEI16@{SR}", "-c", "1", str(aiff), str(wav)], check=True)
    audio, _ = read_wav(wav)
    loud = np.flatnonzero(np.abs(audio) > 0.01)
    return audio[max(0, loud[0] - 800):loud[-1] + 800] if len(loud) else audio


# ---- the brain


def config(home: Path, *, fake: bool, stream: str) -> str:
    stt = (f'use = "tones"\n\n[stt.tones]\nwords = "{home / "words.json"}"\n' if fake else 'use = "mlx_whisper"\n')
    return f"""\
[chat]
use = "none"

[harness]
use = "claude"

[connections]
use = "fake"

[stt]
{stt}
[tts]
use = "none"
fallback = ""

[audio]
use = "wav"

[audio.wav]
mic = "{home / "mic.wav"}"
dir = "{home / "speech"}"

[dictation]
use = "plain"
keep_history = false
stream = "{stream}"

[heartbeat]
enabled = false

[hands]
enabled = false

[memory]
enabled = false

[routines]
enabled = false
"""


class Brain:
    """A brain process on `home`, and the app's end of its socket. Every event is kept with its arrival time."""

    def __init__(self, home: Path, proc, reader, writer):
        self.home = home
        self._proc = proc
        self._reader = reader
        self._writer = writer
        self.events: list[tuple[float, dict]] = []
        self._changed = asyncio.Event()
        self._task = asyncio.create_task(self._read())

    @classmethod
    async def start(cls, home: Path, *, fake: bool, stream: str = "preview", timeout_s: float = 300,
                    src: Path | None = None) -> Brain:
        """`src`: run the brain from this source tree instead (another version, to compare)."""
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.toml").write_text(config(home, fake=fake, stream=stream))
        (home / "logs").mkdir(exist_ok=True)
        stderr = open(home / "logs" / "brain.stderr", "wb")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "milo.server",
            env={**os.environ, "MILO_HOME": str(home), **({"PYTHONPATH": str(src)} if src else {})},
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=stderr,
            start_new_session=True)
        stderr.close()
        try:
            reader, writer = await _connect(home / "run" / "brain.sock")
            brain = cls(home, proc, reader, writer)
            await brain._ready(timeout_s)
        except BaseException:
            await _stop(proc)
            raise
        return brain

    async def _ready(self, timeout_s: float) -> None:
        """Wait until the speech models are loaded (brain.log says so)."""
        log = self.home / "logs" / "brain.log"
        deadline = time.monotonic() + timeout_s
        while "stt engine ready" not in (log.read_text(errors="replace") if log.exists() else ""):
            if "stt engine failed" in (log.read_text(errors="replace") if log.exists() else ""):
                raise RuntimeError(f"the speech model failed to load; see {log}")
            if time.monotonic() > deadline or self._proc.returncode is not None:
                raise RuntimeError(f"the brain wasn't ready after {timeout_s:.0f}s; see {log}")
            await asyncio.sleep(0.1)

    async def _read(self) -> None:
        while line := await self._reader.readline():
            self.events.append((time.monotonic(), json.loads(line)))
            self._changed.set()

    async def send(self, message: dict) -> float:
        self._writer.write((json.dumps(message) + "\n").encode())
        await self._writer.drain()
        return time.monotonic()

    async def wait(self, test, since: float, timeout_s: float) -> tuple[float, dict] | None:
        """The first event after `since` that passes `test`."""
        deadline = time.monotonic() + timeout_s
        while True:
            hit = next(((t, e) for t, e in self.events if t >= since and test(e)), None)
            if hit is not None or time.monotonic() > deadline:
                return hit
            self._changed.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._changed.wait(), max(0.01, deadline - time.monotonic()))

    async def close(self) -> None:
        self._writer.close()
        self._task.cancel()
        await _stop(self._proc)


# ---- one dictation


@dataclass
class Run:
    case: str
    lang: str
    seconds: float
    stream: str
    text: str = ""
    paste_s: float | None = None  # release to the last paste
    first_partial_s: float | None = None  # speech began to the first live words
    partials: int = 0  # live word updates before the release
    state_s: float | None = None  # key-down to the listening state
    errors: int = 0
    lost: int = 0  # words of the script missing from the text
    words: int = 0
    problems: list[str] = field(default_factory=list)


async def dictate(brain: Brain, case: Case, takes: list[np.ndarray], stream: str) -> Run:
    """Hold the dictation key for the length of each take while the brain hears it, the way the app does: a
    second take is pressed `case.again_after_s` after the first was let go."""
    since = time.monotonic()
    await brain.send({"type": "set_setting", "section": "dictation", "key": "stream", "value": stream})
    switched = await brain.wait(lambda e: e["type"] == "settings", since, 5)
    if switched is None or switched[1].get("error"):
        raise RuntimeError(f"the brain didn't switch the dictation stream: {switched}")
    mic = brain.home / "mic.wav"
    downs, releases = [], []
    for audio in takes:
        if releases:
            await asyncio.sleep(max(0.0, releases[-1] + case.again_after_s - time.monotonic()))
        write_wav(mic.with_suffix(".tmp"), audio, SR)
        os.replace(mic.with_suffix(".tmp"), mic)
        mic.with_suffix(".json").write_text(json.dumps({"pressed_at": time.time()}))  # a late mic misses words
        down = await brain.send({"type": "listen_start", "mode": "dictate", "tentative": True})
        await asyncio.sleep(max(0.0, down + SHOW_AFTER_S - time.monotonic()))
        await brain.send({"type": "listen_confirm"})
        await asyncio.sleep(max(0.0, down + len(audio) / SR - time.monotonic()))
        downs.append(down)
        releases.append(await brain.send({"type": "listen_stop"}))
    seconds = sum(len(a) for a in takes) / SR
    release = releases[-1]
    done = await brain.wait(lambda e: e == {"type": "state", "state": "idle"}, release, 60 + seconds)
    if done is None:
        raise RuntimeError(f"{case.id}: no paste {60 + seconds:.0f}s after the release")
    events = [(t, e) for t, e in brain.events if downs[0] <= t <= done[0]]
    pastes = [(t, e["text"]) for t, e in events if e["type"] == "dictation"]
    partials = [t for t, e in events if e["type"] == "partial" and t < releases[0]]
    run = Run(case.id, case.lang, round(seconds, 1), stream, text=" ".join(text for _, text in pastes))
    after = [t for t, _ in pastes if t >= release]
    run.paste_s = round(after[-1] - release, 3) if after else None
    run.first_partial_s = round(partials[0] - (downs[0] + case.lead_s), 3) if partials else None
    run.partials = len(partials)
    shown = [next((t for t, e in events if t >= down and e == {"type": "state", "state": "dictating"}), None)
             for down in downs]
    run.state_s = None if None in shown else round(max(t - down for t, down in zip(shown, downs)), 3)
    score(run, case.script)
    return run


def score(run: Run, script: str) -> None:
    ref, hyp = words(script), words(run.text)
    subs, dels, ins = align(ref, hyp)
    run.errors, run.lost, run.words = subs + dels + ins, dels, len(ref)


# ---- checks


def check(runs: list[Run], limits: Limits) -> None:
    """Note each run's problems against `limits` and the "off" run of the same case."""
    off = {r.case: r for r in runs if r.stream in ("off", "whole")}
    for run in runs:
        if run.stream == "whole":
            continue
        if run.stream == "off":
            if run.state_s is None or run.state_s > limits.state_s:
                run.problems.append(f"listening state {run.state_s}s after key-down (limit {limits.state_s:.2f}s)")
            continue
        base = off.get(run.case)
        if base is not None and run.lost > base.lost + limits.extra_lost:
            run.problems.append(f"lost {run.lost} words, off lost {base.lost}")
        if base is not None and run.errors > base.errors + limits.extra_lost:
            run.problems.append(f"{run.errors} word errors, off had {base.errors}")
        limit = limits.paste_s if run.seconds <= 20 else limits.paste_long_s
        if run.paste_s is None and run.text.strip() and run.stream != "type":
            run.problems.append("nothing pasted after the release")
        elif run.paste_s is not None and run.paste_s > limit:
            run.problems.append(f"paste {run.paste_s:.2f}s after the release (limit {limit:.2f}s)")
        if run.stream != "off":
            if run.first_partial_s is None:
                run.problems.append("no live words while speaking")
            elif run.first_partial_s > limits.first_partial_s:
                run.problems.append(f"first live words {run.first_partial_s:.2f}s after speech began "
                                    f"(limit {limits.first_partial_s:.2f}s)")
        if run.state_s is None or run.state_s > limits.state_s:
            run.problems.append(f"listening state {run.state_s}s after key-down (limit {limits.state_s:.2f}s)")


def table(runs: list[Run]) -> str:
    def s(value: float | None) -> str:
        return "-" if value is None else f"{value:.2f}"

    lines = [f"{'case':24} {'secs':>5} {'stream':8} {'paste':>6} {'1st live':>8} {'lives':>5} {'state':>6} "
             f"{'errors':>8} {'lost':>5}  problems"]
    for r in runs:
        lines.append(f"{r.case:24} {r.seconds:5.1f} {r.stream:8} {s(r.paste_s):>6} {s(r.first_partial_s):>8} "
                     f"{r.partials:5d} {s(r.state_s):>6} {r.errors:3d}/{r.words:<4d} {r.lost:5d}  "
                     f"{'; '.join(r.problems) or 'ok'}")
    for stream in dict.fromkeys(r.stream for r in runs):
        rs = [r for r in runs if r.stream == stream]
        total = sum(r.words for r in rs)
        pastes = sorted(r.paste_s for r in rs if r.paste_s is not None)
        lines.append(f"{stream}: word error {sum(r.errors for r in rs) / max(1, total):.1%}, lost "
                     f"{sum(r.lost for r in rs)} of {total} words, median paste "
                     f"{s(pastes[len(pastes) // 2] if pastes else None)}s")
    return "\n".join(lines)


# ---- running it


async def run(cases: list[Case], root: Path, *, fake: bool, streams: tuple[str, ...], reps: int = 1,
              cache: Path | None = None, limits: Limits | None = None, src: Path | None = None) -> list[Run]:
    """Every case once per stream (and rep) through one brain on `root`, checked against `limits`."""
    cache = cache or root / "clips"
    codec = ToneCodec(vocabulary()) if fake else None
    recordings = {c.id: [recording(take, fake=fake, cache=cache, codec=codec) for take in c.takes] for c in cases}
    home = root / "home"
    home.mkdir(parents=True, exist_ok=True)
    if fake:
        (home / "words.json").write_text(json.dumps(codec.words))
    runs: list[Run] = []
    brain = await Brain.start(home, fake=fake, src=src)
    try:
        for _ in range(reps):
            for case in cases:
                for stream in dict.fromkeys(streams + case.streams):
                    runs.append(await dictate(brain, case, recordings[case.id], stream))
                    await asyncio.sleep(0.3)
    finally:
        await brain.close()
    if fake and "off" not in streams:  # to compare: what "off" hears, the whole recording in one pass
        for case in cases:
            takes = recordings[case.id]
            off = Run(case.id, case.lang, round(sum(len(a) for a in takes) / SR, 1), "whole",
                      text=" ".join(" ".join(codec.hear(audio)) for audio in takes))
            score(off, case.script)
            runs.append(off)
    check(runs, limits or (FAKE if fake else REAL))
    return runs


@contextlib.contextmanager
def model_lock():
    """The shared lock for loading real speech models on this Mac (see the other tracks' rules)."""
    while True:
        try:
            MODEL_LOCK.mkdir()
            break
        except FileExistsError:
            print("waiting for the model lock", MODEL_LOCK, flush=True)
            time.sleep(5)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            MODEL_LOCK.rmdir()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m milo.eval.dictation", description=__doc__.splitlines()[0])
    parser.add_argument("--fake", action="store_true", help="tones and the tone transcriber instead of Whisper")
    parser.add_argument("--only", help="comma-separated case ids; 'gate' for the pytest set")
    parser.add_argument("--streams", default="preview,off", help="comma-separated: preview, type, off")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--root", help="the throwaway workspace (default: a new folder in /tmp)")
    parser.add_argument("--clips", default="/tmp/milo-e2e-clips", help="where rendered recordings are kept")
    parser.add_argument("--json", help="also write the runs here")
    parser.add_argument("--brain-src", help="run the brain from this source folder (an older version, to compare)")
    args = parser.parse_args(argv)

    wanted = set(GATE if args.only == "gate" else args.only.split(",")) if args.only else None
    cases = [c for c in CASES if wanted is None or c.id in wanted]
    root = Path(args.root or tempfile.mkdtemp(prefix="milo-e2e-dictation-", dir="/tmp")).resolve()
    if not str(root).startswith(("/tmp", "/private/tmp", "/var/folders", "/private/var/folders")):
        raise SystemExit(f"refusing to use {root}: only a throwaway folder under /tmp")
    streams = tuple(args.streams.split(","))
    print(f"{len(cases)} dictation(s) x {streams} in {root}" + (" (tones)" if args.fake else " (Whisper)"),
          flush=True)
    lock = contextlib.nullcontext() if args.fake else model_lock()
    with lock:
        runs = asyncio.run(run(cases, root, fake=args.fake, streams=streams, reps=args.reps, cache=Path(args.clips),
                               src=Path(args.brain_src).resolve() if args.brain_src else None))
    print(table(runs))
    if args.json:
        Path(args.json).write_text(json.dumps([asdict(r) for r in runs], indent=1, ensure_ascii=False))
    failed = [r for r in runs if r.problems]
    shutil.rmtree(root / "home" / "speech", ignore_errors=True)
    if failed:
        raise SystemExit(f"{len(failed)} of {len(runs)} run(s) failed")


if __name__ == "__main__":
    main()
