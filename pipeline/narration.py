"""Stage 1: narration — Gemini 3.8 Flash TTS, one WAV per shot."""

from __future__ import annotations

import array
import base64
import json
import time
import wave
from pathlib import Path
from typing import Any, Dict, Optional

from .common import (
    NARRATION,
    OUT,
    Cache,
    Config,
    Storyboard,
    ensure_dirs,
    ffprobe_duration,
    log_run,
    retry,
    silence_wav,
)

try:
    from google import genai
except ImportError:
    genai = None


class GeminiTTS:
    def __init__(self, cfg: Config):
        if not cfg.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        if genai is None:
            raise RuntimeError("google-genai is not installed")
        self.client = genai.Client(
            api_key=cfg.gemini_api_key,
            http_options={"api_version": "v1beta"},
        )
        self.model = "gemini-3.8-flash-tts"

    @retry(attempts=3, base_delay=2.0)
    def synthesize(self, text: str, voice: str, style: str, out_path: Path) -> float:
        interaction = self.client.interactions.create(
            model=self.model,
            input=[
                {
                    "type": "user_input",
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                            "annotations": [{"type": "speech_metadata", "style": style}],
                        }
                    ],
                }
            ],
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": voice}]},
        )

        audio_bytes = self._extract_audio(interaction)
        out_path.write_bytes(audio_bytes)
        return ffprobe_duration(out_path)

    @staticmethod
    def _extract_audio(interaction: Any) -> bytes:
        try:
            data = interaction.output_audio.data
            if isinstance(data, bytes):
                return data
            return base64.b64decode(data)
        except Exception:
            pass

        try:
            for step in interaction.steps:
                for content in step.content:
                    if getattr(content, "type", None) == "audio":
                        data = content.data
                        return data if isinstance(data, bytes) else base64.b64decode(data)
        except Exception:
            pass

        if isinstance(interaction, dict):
            try:
                data = interaction["output_audio"]["data"]
                return data if isinstance(data, bytes) else base64.b64decode(data)
            except Exception:
                pass

        raise RuntimeError("No audio data found in Gemini TTS response")


class NarrationStage:
    def __init__(self, cfg: Config, story: Storyboard, cache: Cache):
        self.cfg = cfg
        self.story = story
        self.cache = cache

    @staticmethod
    def _has_audible_audio(path: Path) -> bool:
        try:
            with wave.open(str(path), "rb") as wav:
                frames = wav.readframes(wav.getnframes())
            if wav.getsampwidth() != 2:
                return bool(frames)
            samples = array.array("h")
            samples.frombytes(frames)
            if not samples:
                return False
            rms = (sum(value * value for value in samples) / len(samples)) ** 0.5
            return rms > 1.0
        except (wave.Error, EOFError, ValueError, OSError):
            return False

    def run(self, only_shot: Optional[str] = None, force: bool = False) -> Dict[str, float]:
        ensure_dirs()
        timing: Dict[str, float] = {}
        voice = self.story.narration_cfg.get("voice", "Kore")
        style = self.story.narration_cfg.get("style", "calm, warm, unhurried, intimate")

        backend = None
        try:
            backend = GeminiTTS(self.cfg)
        except Exception as exc:
            print(f"  ! Gemini TTS unavailable: {exc}")
            if not self.cfg.allow_fallbacks:
                raise

        for shot in self.story.shots:
            sid = shot["id"]
            if only_shot and sid != only_shot:
                existing = NARRATION / f"{sid}.wav"
                timing[sid] = ffprobe_duration(existing) if existing.exists() else float(shot["duration"])
                continue

            text = (shot.get("narration") or "").strip()
            out = NARRATION / f"{sid}.wav"
            key = self.cache.key(
                {
                    "text": text,
                    "voice": voice,
                    "style": style,
                    "model": self.story.narration_cfg.get("model", "gemini-3.8-flash-tts"),
                    "shot": sid,
                }
            )

            if (
                not force
                and out.exists()
                and self._has_audible_audio(out)
                and self.cache.hit("narration", key, ".wav")
            ):
                dur = ffprobe_duration(out)
                timing[sid] = dur if dur > 0.1 else float(shot["duration"])
                log_run(
                    {
                        "stage": "narration",
                        "shot_id": sid,
                        "model": "gemini-3.8-flash-tts",
                        "params": {"voice": voice, "style": style},
                        "seed": None,
                        "latency_s": 0.0,
                        "gpu_minutes": 0.0,
                        "cost_usd": 0.0,
                        "cached": True,
                        "output": str(out),
                    }
                )
                continue

            start = time.perf_counter()
            try:
                if backend is None or not text:
                    raise RuntimeError("TTS backend unavailable or narration empty")
                duration = backend.synthesize(text, voice, style, out)
                fallback = False
                model = "gemini-3.8-flash-tts"
            except Exception as exc:
                if not self.cfg.allow_fallbacks:
                    raise
                print(f"  ! narration fallback for {sid}: {exc}")
                silence_wav(out, 0.05)
                duration = float(shot["duration"])
                fallback = True
                model = "fallback:silence"

            latency = time.perf_counter() - start
            timing[sid] = duration
            if not fallback:
                self.cache.write_meta(
                    "narration",
                    key,
                    {"shot": sid, "text": text, "voice": voice, "style": style},
                )
                cached_wav = self.cache.path("narration", key, ".wav")
                if out.exists() and out.resolve() != cached_wav.resolve():
                    cached_wav.write_bytes(out.read_bytes())
            log_run(
                {
                    "stage": "narration",
                    "shot_id": sid,
                    "model": model,
                    "params": {"voice": voice, "style": style},
                    "seed": None,
                    "latency_s": round(latency, 3),
                    "gpu_minutes": 0.0,
                    "cost_usd": 0.0,
                    "cached": False,
                    "fallback": fallback,
                    "output": str(out),
                }
            )

        (OUT / "timing.json").write_text(
            json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return timing


if __name__ == "__main__":
    import argparse
    from .common import CACHE, ROOT

    parser = argparse.ArgumentParser(description="Run narration stage.")
    parser.add_argument("--story", type=Path, default=ROOT / "storyboard.json")
    parser.add_argument("--shot", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    NarrationStage(Config.load(), Storyboard(args.story), Cache(CACHE)).run(args.shot, args.force)
