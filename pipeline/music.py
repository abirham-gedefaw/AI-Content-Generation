"""Stage 4: music — ACE-Step 1.5 candidates or procedural ambient score fallback."""

from __future__ import annotations

import math
import shutil
import struct
import sys
import time
import wave
from pathlib import Path

from .common import MUSIC, Cache, Config, Storyboard, ensure_dirs, log_run


class ACEStepBackend:
    def __init__(self, cfg: Config):
        if not cfg.acestep_dir:
            raise RuntimeError("ACESTEP_DIR not set")
        sys.path.insert(0, str(Path(cfg.acestep_dir)))
        from acestep.handler import AceStepHandler  # type: ignore
        from acestep.inference import GenerationConfig, GenerationParams, generate_music  # type: ignore
        from acestep.llm_inference import LLMHandler  # type: ignore

        self.GenerationParams = GenerationParams
        self.GenerationConfig = GenerationConfig
        self.generate_music = generate_music
        self.dit = AceStepHandler()
        self.llm = LLMHandler()
        device = "cuda" if shutil.which("nvidia-smi") else "cpu"
        self.dit.initialize_service(
            project_root=cfg.acestep_dir,
            config_path=cfg.acestep_config,
            device=device,
        )
        self.llm.initialize(
            checkpoint_dir=str(Path(cfg.acestep_dir) / "checkpoints"),
            lm_model_path=cfg.acestep_lm,
            backend="vllm" if device == "cuda" else "pt",
            device=device,
        )

    def generate(
        self,
        caption: str,
        duration: float,
        bpm: int,
        seed: int,
        out: Path,
        candidates: int = 3,
    ) -> Path:
        params = self.GenerationParams(
            caption=caption,
            lyrics="[Instrumental]",
            instrumental=True,
            bpm=int(bpm) if bpm else None,
            duration=float(duration),
        )
        n_cand = max(1, min(4, candidates))
        config = self.GenerationConfig(
            batch_size=n_cand,
            audio_format="wav",
            seeds=[int(seed) + i for i in range(n_cand)],
            use_random_seed=False,
        )
        result = self.generate_music(self.dit, self.llm, params, config, save_dir=str(out.parent))
        if not result.success or not result.audios:
            raise RuntimeError(f"ACE-Step failed: {result.error}")
        chosen = Path(result.audios[0]["path"])
        if chosen.resolve() != out.resolve():
            shutil.copy2(chosen, out)
        return out


class ProceduralScore:
    """A small original ambient score, generated with sine waves.
    Always available, royalty-free, and useful when ACE-Step is not installed."""

    def generate(self, duration: float, out: Path, bpm: int = 68) -> Path:
        sr = 48000
        n = int(duration * sr)
        chords = [
            [130.81, 155.56, 196.00],  # C minor
            [116.54, 146.83, 174.61],  # Bb minor
            [103.83, 130.81, 155.56],  # Ab major
            [116.54, 146.83, 196.00],  # Bb
        ]
        with wave.open(str(out), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            for i in range(n):
                t = i / sr
                chord = chords[int(t / 4.0) % len(chords)]
                sample = 0.0
                for j, f in enumerate(chord):
                    sample += math.sin(2 * math.pi * f * t + j * 0.4) * 0.055
                env = 0.55 + 0.45 * math.sin(2 * math.pi * 0.04 * t)
                sample += math.sin(2 * math.pi * 523.25 * t) * 0.006 * env
                val = int(max(-1.0, min(1.0, sample * env)) * 32767)
                w.writeframesraw(struct.pack("<h", val))
        return out


class MusicStage:
    def __init__(self, cfg: Config, story: Storyboard, cache: Cache):
        self.cfg = cfg
        self.story = story
        self.cache = cache

    def run(self, total_duration: float, force: bool = False) -> Path:
        ensure_dirs()
        out = MUSIC / "score.wav"
        m = self.story.music_cfg
        caption = m.get("caption", "Sparse, warm, unhurried instrumental, no vocals.")
        bpm = int(m.get("bpm", 68))
        seed = int(m.get("seed", 42))
        candidates = int(m.get("candidates", 3))
        duration = max(10.0, total_duration + 2.0)

        key = self.cache.key(
            {
                "caption": caption,
                "bpm": bpm,
                "seed": seed,
                "duration": round(duration, 2),
                "candidates": candidates,
                "backend": "acestep" if self.cfg.acestep_dir else "procedural",
            }
        )
        if not force and out.exists() and self.cache.hit("music", key, ".wav"):
            log_run(
                {
                    "stage": "music",
                    "shot_id": None,
                    "model": "ace-step-1.5" if self.cfg.acestep_dir else "procedural-score",
                    "params": {"caption": caption, "bpm": bpm},
                    "seed": seed,
                    "latency_s": 0.0,
                    "gpu_minutes": 0.0,
                    "cost_usd": 0.0,
                    "cached": True,
                    "output": str(out),
                }
            )
            return out

        start = time.perf_counter()
        fallback = False
        try:
            if not self.cfg.acestep_dir:
                raise RuntimeError("ACESTEP_DIR not set")
            backend = ACEStepBackend(self.cfg)
            backend.generate(caption, duration, bpm, seed, out, candidates)
            model = "ace-step-1.5"
        except Exception as exc:
            if not self.cfg.allow_fallbacks:
                raise
            print(f"  ! music fallback: {exc}")
            ProceduralScore().generate(duration, out, bpm)
            model = "procedural-score"
            fallback = True

        latency = time.perf_counter() - start
        gpu_minutes = round(latency / 60.0, 3) if model == "ace-step-1.5" else 0.0
        self.cache.write_meta("music", key, {"caption": caption, "bpm": bpm, "seed": seed})
        if out.exists():
            self.cache.path("music", key, ".wav").write_bytes(out.read_bytes())
        log_run(
            {
                "stage": "music",
                "shot_id": None,
                "model": model,
                "params": {"caption": caption, "bpm": bpm},
                "seed": seed,
                "latency_s": round(latency, 3),
                "gpu_minutes": gpu_minutes,
                "cost_usd": 0.0,
                "cached": False,
                "fallback": fallback,
                "output": str(out),
            }
        )
        return out


if __name__ == "__main__":
    import argparse
    from .common import CACHE, ROOT, load_timing

    parser = argparse.ArgumentParser(description="Run music stage.")
    parser.add_argument("--story", type=Path, default=ROOT / "storyboard.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    story = Storyboard(args.story)
    timing = load_timing(story)
    total = sum(float(timing.get(s["id"], s["duration"])) for s in story.shots)
    total += float(story.meta["end_card"].get("duration", 2.5))
    MusicStage(Config.load(), story, Cache(CACHE)).run(total, args.force)
