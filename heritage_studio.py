#!/usr/bin/env python3
"""
Heritage Short Studio
=====================
A reproducible, multi-model pipeline for 60–90 second heritage films.

Stages
------
0. script     — Gemini 3.8 Flash-Lite subtitle translation / storyboard helpers.
1. narration  — Gemini 3.8 Flash TTS, one WAV per shot.
2. keyframes  — Cloudflare Workers AI FLUX, character sheet + one still per shot.
3. shots      — Wan 2.2 TI2V-5B image-to-video, or FFmpeg Ken Burns fallback.
4. music      — ACE-Step 1.5 candidates, or procedural score fallback.
5. assemble   — FFmpeg: concat, duck, subtitles, loudness, end card, both ratios.

The storyboard is the contract. Every stage reads it and writes only its outputs.
Every model call is logged to runs.jsonl.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Dict, List, Optional

from pipeline import (
    CACHE,
    ROOT,
    STAGES,
    AssemblyStage,
    Cache,
    Config,
    KeyframeStage,
    MusicStage,
    NarrationStage,
    ScriptStage,
    ShotsStage,
    Storyboard,
    ensure_dirs,
    load_timing,
    log_run,
)
from pipeline.common import resolve_ffmpeg


def run_pipeline(
    cfg: Config,
    story_path: Path,
    stages: List[str],
    aspect: str,
    only_shot: Optional[str] = None,
    force: bool = False,
) -> None:
    ensure_dirs()
    story = Storyboard(story_path)
    cache = Cache(CACHE)

    print(f"\n▶ {story.meta['title']}  ({len(story.shots)} shots)")
    print(f"  stages: {', '.join(stages)}\n")

    ScriptStage(cfg, story, cache).ensure_subtitles(force=False)

    timing: Dict[str, float] = {}
    if "narration" in stages:
        print("① narration")
        timing = NarrationStage(cfg, story, cache).run(only_shot, force)
    else:
        timing = load_timing(story)

    if "keyframes" in stages:
        print("② keyframes")
        KeyframeStage(cfg, story, cache).run(only_shot, force)

    if "shots" in stages:
        print("③ moving shots")
        ShotsStage(cfg, story, cache).run(timing, only_shot, force)

    total = sum(float(timing.get(s["id"], s["duration"])) for s in story.shots)
    total += float(story.meta["end_card"].get("duration", 2.5))

    if "music" in stages:
        print("④ music")
        MusicStage(cfg, story, cache).run(total, force)

    if "assemble" in stages:
        print("⑤ assemble")
        aspects = ["9:16", "16:9"] if aspect == "both" else [aspect]
        assembler = AssemblyStage(cfg, story, cache)
        for a in aspects:
            print(f"  → {a}")
            out = assembler.run(timing, a, force)
            print(f"    {out}")

    print("\n✔ done. See runs.jsonl for every model call.")


def run_smoke_test(cfg: Config) -> int:
    """Verify configured providers and local tools, logging latency to runs.jsonl."""
    ensure_dirs()
    print("▶ Smoke test")
    print(f"  ffmpeg: {resolve_ffmpeg()}")
    print(f"  gemini_api_key: {'set' if cfg.gemini_api_key else 'missing (will use fallback)'}")
    print(
        f"  cloudflare: {'set' if cfg.cf_account_id and cfg.cf_api_token else 'missing (will use fallback)'}"
    )
    print(f"  wan_dir: {cfg.wan_dir or 'unset (will use Ken Burns fallback)'}")
    print(f"  acestep_dir: {cfg.acestep_dir or 'unset (will use procedural score fallback)'}")

    start = time.perf_counter()
    log_run(
        {
            "stage": "smoke-test",
            "shot_id": None,
            "model": "system-check",
            "params": {
                "gemini": bool(cfg.gemini_api_key),
                "cloudflare": bool(cfg.cf_account_id and cfg.cf_api_token),
                "wan": bool(cfg.wan_dir),
                "acestep": bool(cfg.acestep_dir),
            },
            "seed": None,
            "latency_s": round(time.perf_counter() - start, 3),
            "gpu_minutes": 0.0,
            "cost_usd": 0.0,
            "cached": False,
            "output": None,
        }
    )
    print("✔ smoke test logged to runs.jsonl")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Heritage Short Studio — a reproducible multi-model film pipeline."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Validate storyboard.json against the schema.")
    p_validate.add_argument("--story", type=Path, default=ROOT / "storyboard.json")

    p_run = sub.add_parser("run", help="Run the full pipeline or selected stages.")
    p_run.add_argument("--story", type=Path, default=ROOT / "storyboard.json")
    p_run.add_argument(
        "--stages",
        default=",".join(STAGES),
        help="Comma-separated stages (default: all).",
    )
    p_run.add_argument("--aspect", choices=["9:16", "16:9", "both"], default="both")
    p_run.add_argument("--shot", default=None, help="Only regenerate this shot id.")
    p_run.add_argument("--force", action="store_true", help="Bypass cache.")

    p_regen = sub.add_parser("regen", help="Regenerate one shot or one stage.")
    p_regen.add_argument("--story", type=Path, default=ROOT / "storyboard.json")
    p_regen.add_argument("--stage", required=True, choices=list(STAGES))
    p_regen.add_argument("--shot", default=None)
    p_regen.add_argument("--aspect", choices=["9:16", "16:9", "both"], default="both")
    p_regen.add_argument("--force", action="store_true", default=True)

    p_radio = sub.add_parser(
        "radio-cut",
        aliases=["radio"],
        help="Phase 1 prototype: narration + placeholder score on a black screen.",
    )
    p_radio.add_argument("--story", type=Path, default=ROOT / "storyboard.json")
    p_radio.add_argument("--force", action="store_true")

    sub.add_parser(
        "smoke-test",
        aliases=["smoke"],
        help="Check configured providers and log a smoke test entry.",
    )

    args = parser.parse_args(argv)
    cfg = Config.load()

    if args.command == "validate":
        story = Storyboard(args.story)
        total = sum(float(s["duration"]) for s in story.shots)
        print(f"✔ valid: {story.meta['title']}")
        print(f"  {len(story.shots)} shots, storyboard duration {total:.1f}s")
        if not (55 <= total <= 95):
            print("  ! warning: duration is outside the 60–90s target once narration is added")
        return 0

    if args.command == "run":
        stages = [s.strip() for s in args.stages.split(",") if s.strip() in STAGES]
        if not stages:
            print("No valid stages given.")
            return 2
        run_pipeline(cfg, args.story, stages, args.aspect, args.shot, args.force)
        return 0

    if args.command == "regen":
        run_pipeline(cfg, args.story, [args.stage], args.aspect, args.shot, True)
        return 0

    if args.command in ("radio-cut", "radio"):
        ensure_dirs()
        story = Storyboard(args.story)
        cache = Cache(CACHE)
        timing = NarrationStage(cfg, story, cache).run(force=args.force)
        out = AssemblyStage(cfg, story, cache).run_radio_cut(timing)
        print(f"✔ radio cut written to {out}")
        return 0

    if args.command in ("smoke-test", "smoke"):
        return run_smoke_test(cfg)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
