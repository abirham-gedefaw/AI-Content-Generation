"""Stage 2: keyframes — Cloudflare Workers AI FLUX, character sheet + per-shot stills."""

from __future__ import annotations

import base64
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
# pyrefly: ignore[missing-import]
from PIL import Image, ImageDraw, ImageFont

from .common import KEYFRAMES, Cache, Config, Storyboard, ensure_dirs, log_run, retry, sha256_file


class CloudflareFLUX:
    def __init__(self, cfg: Config):
        if not cfg.cf_account_id or not cfg.cf_api_token:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN not set")
        self.account_id = cfg.cf_account_id
        self.token = cfg.cf_api_token
        self.model = cfg.cf_flux_model

    @retry(attempts=3, base_delay=2.0)
    def generate(
        self,
        prompt: str,
        seed: int,
        out_path: Path,
        width: int = 1024,
        height: int = 1024,
        reference_image: Optional[Path] = None,
    ) -> None:
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/run/{self.model}"
        )
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "steps": 4,
            "seed": int(seed),
            "width": int(width),
            "height": int(height),
        }
        if reference_image and reference_image.exists():
            payload["image"] = base64.b64encode(reference_image.read_bytes()).decode("ascii")

        resp = requests.post(url, headers=headers, json=payload, timeout=180)
        if resp.status_code >= 400:
            payload.pop("width", None)
            payload.pop("height", None)
            resp = requests.post(url, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
        data = resp.json()

        img_b64 = None
        try:
            img_b64 = data["result"]["image"]
        except Exception:
            pass
        if not img_b64:
            raise RuntimeError(f"Unexpected Cloudflare response: {str(data)[:500]}")

        if img_b64.startswith("data:"):
            img_b64 = img_b64.split(",", 1)[1]
        out_path.write_bytes(base64.b64decode(img_b64))


class KeyframeStage:
    def __init__(self, cfg: Config, story: Storyboard, cache: Cache):
        self.cfg = cfg
        self.story = story
        self.cache = cache

    def _placeholder(self, shot: Dict[str, Any], out: Path) -> None:
        w, h = 1024, 1024
        img = Image.new("RGB", (w, h), (24, 20, 18))
        draw = ImageDraw.Draw(img)
        for y in range(h):
            t = y / h
            draw.line([(0, y), (w, y)], fill=(int(80 + 80 * t), int(50 + 40 * t), 30))
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 34)
            small = ImageFont.truetype("DejaVuSans.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
            small = font
        draw.text((60, 60), f"PLACEHOLDER — {shot['id']}", font=font, fill=(255, 235, 200))
        body = textwrap.fill(shot.get("keyframe_prompt", "")[:300], width=42)
        draw.text((60, 130), body, font=small, fill=(245, 225, 200))
        img.save(out)

    def run(self, only_shot: Optional[str] = None, force: bool = False) -> None:
        ensure_dirs()
        character = self.story.character
        style = self.story.style_block
        ref_path = KEYFRAMES / "_reference.png"

        backend = None
        try:
            backend = CloudflareFLUX(self.cfg)
        except Exception as exc:
            print(f"  ! Cloudflare FLUX unavailable: {exc}")
            if not self.cfg.allow_fallbacks:
                raise

        if backend and character.get("reference_prompt"):
            key = self.cache.key(
                {
                    "kind": "reference",
                    "prompt": character["reference_prompt"],
                    "style": style,
                    "seed": character.get("seed", 1847),
                }
            )
            if force or not ref_path.exists() or not self.cache.hit("keyframes", key, ".png"):
                start = time.perf_counter()
                try:
                    backend.generate(
                        f"{character['reference_prompt']}\n\nSTYLE: {style}",
                        seed=int(character.get("seed", 1847)),
                        out_path=ref_path,
                    )
                    latency = time.perf_counter() - start
                    self.cache.write_meta("keyframes", key, {"kind": "reference"})
                    self.cache.path("keyframes", key, ".png").write_bytes(ref_path.read_bytes())
                    log_run(
                        {
                            "stage": "keyframes",
                            "shot_id": "_reference",
                            "model": self.cfg.cf_flux_model,
                            "params": {"prompt": character["reference_prompt"]},
                            "seed": character.get("seed", 1847),
                            "latency_s": round(latency, 3),
                            "gpu_minutes": 0.0,
                            "cost_usd": 0.0,
                            "cached": False,
                            "fallback": False,
                            "output": str(ref_path),
                        }
                    )
                except Exception as exc:
                    if not self.cfg.allow_fallbacks:
                        raise
                    print(f"  ! reference sheet fallback: {exc}")
                    log_run(
                        {
                            "stage": "keyframes",
                            "shot_id": "_reference",
                            "model": "fallback:placeholder",
                            "params": {},
                            "seed": None,
                            "latency_s": 0.0,
                            "gpu_minutes": 0.0,
                            "cost_usd": 0.0,
                            "cached": False,
                            "fallback": True,
                            "output": str(ref_path),
                        }
                    )
            else:
                log_run(
                    {
                        "stage": "keyframes",
                        "shot_id": "_reference",
                        "model": self.cfg.cf_flux_model,
                        "params": {},
                        "seed": character.get("seed", 1847),
                        "latency_s": 0.0,
                        "gpu_minutes": 0.0,
                        "cost_usd": 0.0,
                        "cached": True,
                        "output": str(ref_path),
                    }
                )

        for shot in self.story.shots:
            sid = shot["id"]
            if only_shot and sid != only_shot:
                continue
            out = KEYFRAMES / f"{sid}.png"
            char_desc = character.get("description", "")
            prompt = (
                f"{shot['keyframe_prompt']}\n\n"
                f"CHARACTER: {char_desc}\n\n"
                f"STYLE: {style}\n\n"
                "COMPOSITION: subject centred, generous headroom, safe margins for "
                "cropping to both vertical and horizontal, no text, no watermark."
            )
            negative = shot.get(
                "negative_prompt", "text, watermark, logo, deformed hands, extra fingers"
            )
            if negative:
                prompt += f"\nAVOID: {negative}"

            key = self.cache.key(
                {
                    "shot": sid,
                    "prompt": prompt,
                    "seed": shot.get("seed", 1),
                    "model": self.cfg.cf_flux_model,
                    "reference": sha256_file(ref_path) if ref_path.exists() else None,
                }
            )
            if not force and out.exists() and self.cache.hit("keyframes", key, ".png"):
                log_run(
                    {
                        "stage": "keyframes",
                        "shot_id": sid,
                        "model": self.cfg.cf_flux_model,
                        "params": {"prompt": prompt},
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
                if backend is None:
                    raise RuntimeError("Cloudflare backend unavailable")
                backend.generate(
                    prompt,
                    seed=int(shot.get("seed", 1)),
                    out_path=out,
                    reference_image=ref_path,
                )
                fallback = False
                model = self.cfg.cf_flux_model
            except Exception as exc:
                if not self.cfg.allow_fallbacks:
                    raise
                print(f"  ! keyframe fallback for {sid}: {exc}")
                self._placeholder(shot, out)
                fallback = True
                model = "fallback:placeholder"

            latency = time.perf_counter() - start
            self.cache.write_meta("keyframes", key, {"shot": sid, "prompt": prompt})
            if out.exists():
                self.cache.path("keyframes", key, ".png").write_bytes(out.read_bytes())
            log_run(
                {
                    "stage": "keyframes",
                    "shot_id": sid,
                    "model": model,
                    "params": {"prompt": prompt},
                    "seed": shot.get("seed", 1),
                    "latency_s": round(latency, 3),
                    "gpu_minutes": 0.0,
                    "cost_usd": 0.0,
                    "cached": False,
                    "fallback": fallback,
                    "output": str(out),
                }
            )


if __name__ == "__main__":
    import argparse
    from .common import CACHE, ROOT

    parser = argparse.ArgumentParser(description="Run keyframes stage.")
    parser.add_argument("--story", type=Path, default=ROOT / "storyboard.json")
    parser.add_argument("--shot", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    KeyframeStage(Config.load(), Storyboard(args.story), Cache(CACHE)).run(args.shot, args.force)
