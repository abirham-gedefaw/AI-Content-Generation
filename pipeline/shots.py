"""Stage 3: moving shots — Wan 2.2 TI2V-5B or FFmpeg Ken Burns fallback."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional

from .common import (
    FPS_DEFAULT,
    KEYFRAMES,
    SHOTS,
    Cache,
    Config,
    Storyboard,
    ensure_dirs,
    ffmpeg,
    log_run,
    sha256_file,
)


class KenBurnsBackend:
    """Always-available FFmpeg fallback. A still becomes a slow, intentional move."""

    def render(
        self,
        keyframe: Path,
        duration: float,
        out: Path,
        aspect: str,
        motion_prompt: str = "",
    ) -> None:
        w, h = (720, 1280) if aspect == "9:16" else (1280, 720)
        cover = out.with_suffix(".cover.png")
        ffmpeg(
            [
                "-i",
                keyframe,
                "-vf",
                f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1",
                "-frames:v",
                "1",
                cover,
            ]
        )
        frames = max(2, int(duration * FPS_DEFAULT))
        zoom_rate = 0.00045 if "out" in motion_prompt.lower() else 0.00065
        ffmpeg(
            [
                "-loop",
                "1",
                "-i",
                cover,
                "-vf",
                f"zoompan=z='min(zoom+{zoom_rate},1.10)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s={w}x{h}:fps={FPS_DEFAULT},setsar=1",
                "-t",
                f"{duration:.3f}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                out,
            ]
        )
        cover.unlink(missing_ok=True)


class WanLocalBackend:
    """Calls Wan 2.2 TI2V-5B generate.py on a local GPU / Kaggle session."""

    def __init__(self, cfg: Config):
        if not cfg.wan_dir or not cfg.wan_ckpt_dir:
            raise RuntimeError("WAN_DIR / WAN_CKPT_DIR not set")
        self.wan_dir = Path(cfg.wan_dir)
        self.ckpt = Path(cfg.wan_ckpt_dir)

    def render(
        self,
        keyframe: Path,
        duration: float,
        out: Path,
        aspect: str,
        motion_prompt: str = "",
    ) -> None:
        size = "704*1280" if aspect == "9:16" else "1280*704"
        cmd = [
            sys.executable,
            "generate.py",
            "--task",
            "ti2v-5B",
            "--size",
            size,
            "--ckpt_dir",
            str(self.ckpt),
            "--offload_model",
            "True",
            "--convert_model_dtype",
            "--t5_cpu",
            "--image",
            str(keyframe),
            "--prompt",
            motion_prompt or "Gentle, slow, natural movement.",
        ]
        before = set(self.wan_dir.rglob("*.mp4"))
        proc = subprocess.run(
            cmd,
            cwd=str(self.wan_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3600,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Wan failed:\n{proc.stderr[-2000:]}")
        after = set(self.wan_dir.rglob("*.mp4"))
        new = sorted(after - before, key=lambda p: p.stat().st_mtime, reverse=True)
        if not new:
            raise RuntimeError("Wan produced no MP4 output")
        shutil.copy2(new[0], out)


class ShotsStage:
    def __init__(self, cfg: Config, story: Storyboard, cache: Cache):
        self.cfg = cfg
        self.story = story
        self.cache = cache

    def run(
        self,
        timing: Dict[str, float],
        only_shot: Optional[str] = None,
        force: bool = False,
    ) -> None:
        ensure_dirs()
        wan = None
        try:
            wan = WanLocalBackend(self.cfg)
        except Exception as exc:
            print(f"  ! Wan local unavailable: {exc}; using Ken Burns fallback")
            if not self.cfg.allow_fallbacks:
                raise

        kb = KenBurnsBackend()
        for shot in self.story.shots:
            sid = shot["id"]
            if only_shot and sid != only_shot:
                continue
            keyframe = KEYFRAMES / f"{sid}.png"
            out = SHOTS / f"{sid}.mp4"
            duration = max(2.0, float(timing.get(sid, shot["duration"])) + 0.35)
            motion = shot.get("motion_prompt", "")

            key = self.cache.key(
                {
                    "shot": sid,
                    "keyframe": sha256_file(keyframe) if keyframe.exists() else None,
                    "motion": motion,
                    "duration": round(duration, 2),
                    "backend": "wan" if wan else "kenburns",
                    "seed": shot.get("seed", 1),
                }
            )
            if not force and out.exists() and self.cache.hit("shots", key, ".mp4"):
                log_run(
                    {
                        "stage": "shots",
                        "shot_id": sid,
                        "model": "wan2.2-ti2v-5b" if wan else "ffmpeg-kenburns",
                        "params": {"motion": motion},
                        "seed": shot.get("seed", 1),
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
                if wan is None:
                    raise RuntimeError("Wan backend unavailable")
                wan.render(keyframe, duration, out, "16:9", motion)
                model = "wan2.2-ti2v-5b"
                fallback = False
            except Exception as exc:
                if not self.cfg.allow_fallbacks:
                    raise
                print(f"  ! shot fallback for {sid}: {exc}")
                kb.render(keyframe, duration, out, "16:9", motion)
                model = "ffmpeg-kenburns"
                fallback = True

            latency = time.perf_counter() - start
            gpu_minutes = round(latency / 60.0, 3) if model.startswith("wan") else 0.0
            self.cache.write_meta(
                "shots", key, {"shot": sid, "motion": motion, "duration": duration}
            )
            if out.exists():
                self.cache.path("shots", key, ".mp4").write_bytes(out.read_bytes())
            log_run(
                {
                    "stage": "shots",
                    "shot_id": sid,
                    "model": model,
                    "params": {"motion": motion},
                    "seed": shot.get("seed", 1),
                    "latency_s": round(latency, 3),
                    "gpu_minutes": gpu_minutes,
                    "cost_usd": 0.0,
                    "cached": False,
                    "fallback": fallback,
                    "output": str(out),
                }
            )


if __name__ == "__main__":
    import argparse
    from .common import CACHE, ROOT, load_timing

    parser = argparse.ArgumentParser(description="Run moving shots stage.")
    parser.add_argument("--story", type=Path, default=ROOT / "storyboard.json")
    parser.add_argument("--shot", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    story = Storyboard(args.story)
    ShotsStage(Config.load(), story, Cache(CACHE)).run(load_timing(story), args.shot, args.force)
