"""Stage 0 (pre-production): script & subtitle translation via Gemini 3.8 Flash."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .common import Cache, Config, Storyboard, ensure_dirs, log_run, retry

try:
    from google import genai
except ImportError:
    genai = None


class ScriptStage:
    """Translates missing English subtitles or drafts shot prompts via Gemini Flash-Lite."""

    def __init__(self, cfg: Config, story: Storyboard, cache: Cache):
        self.cfg = cfg
        self.story = story
        self.cache = cache
        self.model = "gemini-3.8-flash-lite"

    @retry(attempts=3, base_delay=2.0)
    def _translate_line(self, client: object, text: str, src_lang: str, dst_lang: str) -> str:
        prompt = (
            f"Translate this short-film narration line from {src_lang} to natural, "
            f"concise {dst_lang} suitable for a subtitle (max 2 short lines, no quotes):\n\n{text}"
        )
        resp = client.models.generate_content(model=self.model, contents=prompt)  # type: ignore[attr-defined]
        return (getattr(resp, "text", "") or "").strip()

    def ensure_subtitles(self, force: bool = False) -> bool:
        """Populate missing `subtitle` fields in storyboard.json when narration is non-English."""
        ensure_dirs()
        src_lang = self.story.meta.get("language", "am")
        dst_lang = self.story.meta.get("subtitle_language", "en")
        if src_lang == dst_lang:
            return False

        missing = [s for s in self.story.shots if not (s.get("subtitle") or "").strip()]
        if not missing and not force:
            return False

        if not self.cfg.gemini_api_key or genai is None:
            print("  ! Gemini API unavailable for subtitle translation; keeping existing subtitles.")
            return False

        client = genai.Client(api_key=self.cfg.gemini_api_key)
        updated = False
        for shot in self.story.shots:
            if not force and (shot.get("subtitle") or "").strip():
                continue
            narration = (shot.get("narration") or "").strip()
            if not narration:
                continue
            start = time.perf_counter()
            try:
                translated = self._translate_line(client, narration, src_lang, dst_lang)
                if translated:
                    shot["subtitle"] = translated
                    updated = True
                fallback = False
            except Exception as exc:
                if not self.cfg.allow_fallbacks:
                    raise
                print(f"  ! translation fallback for {shot['id']}: {exc}")
                fallback = True
            latency = time.perf_counter() - start
            log_run(
                {
                    "stage": "script",
                    "shot_id": shot["id"],
                    "model": self.model,
                    "params": {"src": src_lang, "dst": dst_lang},
                    "seed": None,
                    "latency_s": round(latency, 3),
                    "gpu_minutes": 0.0,
                    "cost_usd": 0.0,
                    "cached": False,
                    "fallback": fallback,
                    "output": str(self.story.path),
                }
            )

        if updated:
            self.story.path.write_text(
                json.dumps(self.story.data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return updated


if __name__ == "__main__":
    import argparse
    from .common import CACHE, ROOT

    parser = argparse.ArgumentParser(description="Translate missing subtitles in storyboard.json.")
    parser.add_argument("--story", type=Path, default=ROOT / "storyboard.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    ScriptStage(Config.load(), Storyboard(args.story), Cache(CACHE)).ensure_subtitles(args.force)
