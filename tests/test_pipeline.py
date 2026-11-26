"""Unit tests for Heritage Short Studio."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# pyrefly: ignore[missing-import]
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.assemble import AssemblyStage, _subtitle_style
from pipeline.common import Cache, Config, Storyboard, clean_narration_wav, srt_time, wrap_for_subtitle


def test_storyboard_validates() -> None:
    story = Storyboard(ROOT / "storyboard.json")
    assert story.meta["title"].strip()
    assert 6 <= len(story.shots) <= 14
    total = sum(float(s["duration"]) for s in story.shots) + float(
        story.meta["end_card"]["duration"]
    )
    assert 60.0 <= total <= 90.0
    for s in story.shots:
        assert s.get("subtitle"), f"Shot {s['id']} is missing English subtitle"
        assert s.get("reason"), f"Shot {s['id']} is missing reason"


def test_consent_gate_blocks_unrecorded(tmp_path: Path) -> None:
    data = json.loads((ROOT / "storyboard.json").read_text(encoding="utf-8"))
    data["meta"]["consent"]["required"] = True
    data["meta"]["consent"]["recorded"] = False
    bad = tmp_path / "bad_story.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SystemExit):
        Storyboard(bad)


def test_cache_roundtrip(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    key = cache.key({"shot": "s01", "prompt": "dawn", "seed": 101})
    assert not cache.hit("keyframes", key, ".png")
    cache.path("keyframes", key, ".png").write_bytes(b"fake-png")
    cache.write_meta("keyframes", key, {"shot": "s01"})
    assert cache.hit("keyframes", key, ".png")


def test_narration_noise_cleanup(tmp_path: Path) -> None:
    source = ROOT / "outputs" / "narration" / "s01.wav"
    cleaned = tmp_path / "s01_clean.wav"
    clean_narration_wav(source, cleaned)
    assert cleaned.is_file()
    assert cleaned.stat().st_size > 44


def test_subtitle_wrapping_and_srt_time() -> None:
    assert srt_time(0.0) == "00:00:00,000"
    assert srt_time(65.5) == "00:01:05,500"
    lines = wrap_for_subtitle(
        "Before she left for the market, my grandmother always looked at the sun.", width=42
    )
    assert 1 <= len(lines) <= 2
    assert all(len(line) <= 42 for line in lines)


def test_movie_subtitle_style_is_small_and_bottom_aligned() -> None:
    style = _subtitle_style(font_size=18, margin_v=32)
    assert "FontSize=18" in style
    assert "MarginV=32" in style
    assert "Alignment=2" in style


def test_communication_images_cover_the_traveler_conversation() -> None:
    keyframes = ROOT / "outputs" / "keyframes"
    names = (
        "communication_01_greeting",
        "communication_02_where_going",
        "communication_03_explains_family",
        "communication_04_offer",
        "communication_05_handoff",
    )
    for name in names:
        assert (keyframes / f"{name}_source.png").is_file()
        assert (keyframes / f"{name}_9x16.png").is_file()


def test_build_srt_uses_english_subtitles(tmp_path: Path) -> None:
    story = Storyboard(ROOT / "storyboard.json")
    assembler = AssemblyStage(Config(), story, Cache(tmp_path / "cache"))
    srt_path = tmp_path / "out.srt"
    timing = {s["id"]: float(s["duration"]) for s in story.shots}
    assembler._build_srt(timing, srt_path)
    content = srt_path.read_text(encoding="utf-8")
    assert story.shots[0]["subtitle"][:20] in content
    assert story.shots[0]["narration"] not in content
