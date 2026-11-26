"""Stage 5: assemble — FFmpeg concat, ducking, loudness norm, subtitles, end card, exports."""

from __future__ import annotations

import shutil
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List

# pyrefly: ignore[missing-import]
from PIL import Image, ImageDraw, ImageFont

from .common import (
    ASSEMBLY,
    FINAL,
    FPS_DEFAULT,
    KEYFRAMES,
    MUSIC,
    NARRATION,
    SHOTS,
    Cache,
    Config,
    Storyboard,
    ensure_dirs,
    ffmpeg,
    ffprobe_duration,
    log_run,
    pad_wav,
    clean_narration_wav,
    sha256_file,
    silence_wav,
    srt_time,
    wrap_for_subtitle,
)
from .music import ProceduralScore


def _escape_ffmpeg_filter_path(path: Path) -> str:
    """Escape a filesystem path for FFmpeg's subtitles= filter (handles Windows drive colons)."""
    posix = path.resolve().as_posix()
    return posix.replace(":", r"\:").replace("'", r"\'")


def _subtitle_style(font_size: int, margin_v: int) -> str:
    return (
        f"FontName=DejaVu Sans,FontSize={font_size},"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=1,Shadow=0,"
        f"MarginV={margin_v},Alignment=2"
    )


class AssemblyStage:
    def __init__(self, cfg: Config, story: Storyboard, cache: Cache):
        self.cfg = cfg
        self.story = story
        self.cache = cache

    def _placeholder_image(self, shot: Dict[str, Any], out: Path) -> None:
        img = Image.new("RGB", (1024, 1024), (20, 18, 16))
        draw = ImageDraw.Draw(img)
        for y in range(1024):
            t = y / 1024
            draw.line([(0, y), (1024, y)], fill=(int(70 + 90 * t), int(45 + 45 * t), 30))
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 30)
        except Exception:
            font = ImageFont.load_default()
        draw.text((50, 50), shot["id"], font=font, fill=(255, 230, 200))
        body = textwrap.fill(shot.get("keyframe_prompt", "")[:250], width=40)
        draw.text((50, 110), body, font=font, fill=(240, 220, 200))
        img.save(out)

    def _end_card(self, w: int, h: int, text: str) -> Path:
        out = ASSEMBLY / f"end_card_{w}x{h}.png"
        img = Image.new("RGB", (w, h), (10, 10, 10))
        draw = ImageDraw.Draw(img)
        try:
            title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(28, w // 18))
            sub_font = ImageFont.truetype("DejaVuSans.ttf", max(18, w // 30))
        except Exception:
            title_font = ImageFont.load_default()
            sub_font = title_font
        title = self.story.meta["title"]
        for txt, font, y_off in [(title, title_font, -40), (text, sub_font, 40)]:
            bbox = draw.textbbox((0, 0), txt, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((w - tw) / 2, (h - th) / 2 + y_off), txt, font=font, fill=(235, 225, 210))
        img.save(out)
        return out

    def _normalize_video(self, src: Path, w: int, h: int, duration: float, out: Path) -> None:
        ffmpeg(
            [
                "-i",
                src,
                "-vf",
                f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={FPS_DEFAULT}",
                "-t",
                f"{duration:.3f}",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                out,
            ]
        )

    def _kenburns(
        self,
        image: Path,
        w: int,
        h: int,
        duration: float,
        out: Path,
        motion_prompt: str = "",
    ) -> None:
        cover = out.with_suffix(".cover.png")
        ffmpeg(
            [
                "-i",
                image,
                "-vf",
                f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1",
                "-frames:v",
                "1",
                cover,
            ]
        )
        frames = max(2, int(duration * FPS_DEFAULT))
        motion = motion_prompt.lower()
        if "push" in motion or "close" in motion or "in on" in motion:
            zoom_expression = "min(zoom+0.00065,1.12)"
            x_expression = "iw/2-(iw/zoom/2)"
            y_expression = "ih/2-(ih/zoom/2)"
        elif "walk" in motion or "stroll" in motion or "passes" in motion:
            zoom_expression = "min(zoom+0.00035,1.08)"
            x_expression = "iw/2-(iw/zoom/2)+18*sin(on/120)"
            y_expression = "ih/2-(ih/zoom/2)"
        else:
            zoom_expression = "min(zoom+0.00045,1.10)"
            x_expression = "iw/2-(iw/zoom/2)+10*sin(on/160)"
            y_expression = "ih/2-(ih/zoom/2)+4*cos(on/190)"
        ffmpeg(
            [
                "-loop",
                "1",
                "-i",
                cover,
                "-vf",
                f"zoompan=z='{zoom_expression}':"
                f"x='{x_expression}':y='{y_expression}':"
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

    def _end_card_video(self, png: Path, w: int, h: int, duration: float, out: Path) -> None:
        ffmpeg(
            [
                "-loop",
                "1",
                "-i",
                png,
                "-t",
                f"{duration:.3f}",
                "-vf",
                f"fps={FPS_DEFAULT},scale={w}:{h},setsar=1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                out,
            ]
        )

    def _build_narration_track(
        self,
        timing: Dict[str, float],
        total: float,
        out: Path,
        intro_dur: float = 0.0,
    ) -> None:
        segments: List[Path] = []
        if intro_dur > 0:
            intro_sil = ASSEMBLY / "narr_intro.wav"
            silence_wav(intro_sil, intro_dur)
            segments.append(intro_sil)
        for shot in self.story.shots:
            sid = shot["id"]
            dur = float(timing.get(sid, shot["duration"]))
            src = NARRATION / f"{sid}.wav"
            seg = ASSEMBLY / f"narr_{sid}.wav"
            if src.exists() and ffprobe_duration(src) > 0.06:
                cleaned = ASSEMBLY / f"narr_{sid}_clean.wav"
                clean_narration_wav(src, cleaned)
                pad_wav(cleaned, seg, dur)
            else:
                silence_wav(seg, dur)
            segments.append(seg)

        end_dur = float(self.story.meta["end_card"].get("duration", 2.5))
        end_sil = ASSEMBLY / "narr_end.wav"
        silence_wav(end_sil, end_dur)
        segments.append(end_sil)

        list_file = ASSEMBLY / "narration_concat.txt"
        list_file.write_text(
            "\n".join(f"file '{p.resolve().as_posix()}'" for p in segments),
            encoding="utf-8",
        )
        ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_file,
                "-c:a",
                "pcm_s16le",
                "-ar",
                "48000",
                "-ac",
                "1",
                out,
            ]
        )

    def _mix(self, narration: Path, music: Path, total: float, out: Path) -> None:
        ffmpeg(
            [
                "-i",
                narration,
                "-stream_loop",
                "-1",
                "-i",
                music,
                "-filter_complex",
                "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1.0[voice];"
                "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.30,"
                "afade=t=in:st=0:d=0.8[music];"
                "[music][voice]sidechaincompress=threshold=0.02:ratio=6:"
                "attack=300:release=1500[ducked];"
                "[voice][ducked]amix=inputs=2:duration=first:dropout_transition=2,"
                "loudnorm=I=-14:TP=-1:LRA=11[out]",
                "-map",
                "[out]",
                "-t",
                f"{total:.3f}",
                "-c:a",
                "pcm_s16le",
                out,
            ]
        )

    def _build_srt(self, timing: Dict[str, float], out: Path) -> None:
        t = 0.0
        blocks: List[str] = []
        idx = 1
        for shot in self.story.shots:
            sid = shot["id"]
            dur = float(timing.get(sid, shot["duration"]))
            sub_text = (shot.get("subtitle") or shot.get("narration") or "").strip()
            lines = wrap_for_subtitle(sub_text, 42)
            if lines:
                blocks.append(
                    f"{idx}\n{srt_time(t)} --> {srt_time(t + dur)}\n" + "\n".join(lines) + "\n"
                )
                idx += 1
            t += dur
        out.write_text("\n".join(blocks), encoding="utf-8")

    def run_radio_cut(self, timing: Dict[str, float]) -> Path:
        """Phase 1 prototype: animated portrait, narration and music with subtitles."""
        ensure_dirs()
        w, h = 720, 1280
        end_dur = float(self.story.meta["end_card"].get("duration", 2.5))
        total = sum(float(timing.get(s["id"], s["duration"])) for s in self.story.shots) + end_dur
        out = FINAL / "radio_cut_9x16.mp4"
        work = ASSEMBLY / "radio_cut"
        work.mkdir(parents=True, exist_ok=True)

        narration_track = work / "narration.wav"
        self._build_narration_track(timing, total, narration_track, intro_dur)

        music_src = MUSIC / "score.wav"
        if not music_src.exists():
            ProceduralScore().generate(total + 2.0, music_src)
        mixed = work / "mixed.wav"
        self._mix(narration_track, music_src, total, mixed)

        srt = work / "subtitles.srt"
        self._build_srt(timing, srt)

        style = _subtitle_style(font_size=18, margin_v=48)
        srt_escaped = _escape_ffmpeg_filter_path(srt)
        portrait = KEYFRAMES / "abba_gebre_hanna_portrait_9x16.png"
        if portrait.exists():
            frames = max(2, int(total * FPS_DEFAULT))
            ffmpeg(
                [
                    "-loop",
                    "1",
                    "-i",
                    portrait,
                    "-i",
                    mixed,
                    "-vf",
                    f"zoompan=z='min(zoom+0.00035,1.08)':"
                    f"x='iw/2-(iw/zoom/2)+14*sin(on/100)':"
                    f"y='ih/2-(ih/zoom/2)':"
                    f"d={frames}:s={w}x{h}:fps={FPS_DEFAULT},"
                    f"subtitles='{srt_escaped}':force_style='{style}',setsar=1",
                    "-t",
                    f"{total:.3f}",
                    "-map",
                    "0:v",
                    "-map",
                    "1:a",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    out,
                ]
            )
        else:
            ffmpeg(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=black:s={w}x{h}:r={FPS_DEFAULT}:d={total:.3f}",
                    "-i",
                    mixed,
                    "-vf",
                    f"subtitles='{srt_escaped}':force_style='{style}'",
                    "-map",
                    "0:v",
                    "-map",
                    "1:a",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    out,
                ]
            )
        log_run(
            {
                "stage": "assemble",
                "shot_id": None,
                "model": "ffmpeg-radio-cut",
                "params": {"aspect": "9:16", "width": w, "height": h},
                "seed": None,
                "latency_s": 0.0,
                "gpu_minutes": 0.0,
                "cost_usd": 0.0,
                "cached": False,
                "output": str(out),
            }
        )
        return out

    def run(self, timing: Dict[str, float], aspect: str, force: bool = False) -> Path:
        ensure_dirs()
        w, h = (720, 1280) if aspect == "9:16" else (1280, 720)
        end_dur = float(self.story.meta["end_card"].get("duration", 2.5))
        intro_dur = 2.5
        communication_dur = 1.2
        intro_total = intro_dur + (communication_dur * 5)
        total = intro_total + sum(
            float(timing.get(s["id"], s["duration"])) for s in self.story.shots
        ) + end_dur

        out = FINAL / f"heritage_short_{aspect.replace(':', 'x')}.mp4"
        margin_v = 52 if aspect == "9:16" else 32
        style = _subtitle_style(font_size=18, margin_v=margin_v)
        manifest = {
            "aspect": aspect,
            "timing": timing,
            "end_card": self.story.meta["end_card"],
            "opening_portrait": sha256_file(KEYFRAMES / "abba_gebre_hanna_portrait_9x16.png")
            if (KEYFRAMES / "abba_gebre_hanna_portrait_9x16.png").exists()
            else sha256_file(KEYFRAMES / "abba_gebre_hanna_portrait.png")
            if (KEYFRAMES / "abba_gebre_hanna_portrait.png").exists()
            else None,
            "opening_duration": intro_total,
            "radio_cut_images": [
                sha256_file(
                    KEYFRAMES
                    / (
                        f"communication_0{i}_{'9x16' if aspect == '9:16' else 'source'}.png"
                    )
                )
                if (
                    KEYFRAMES
                    / (
                        f"communication_0{i}_{'9x16' if aspect == '9:16' else 'source'}.png"
                    )
                ).exists()
                else None
                for i in range(1, 6)
            ],
            "subtitles": [s.get("subtitle", "") for s in self.story.shots],
            "subtitle_style": style,
            "music": sha256_file(MUSIC / "score.wav") if (MUSIC / "score.wav").exists() else None,
            "shots": {
                s["id"]: sha256_file(KEYFRAMES / f"{s['id']}.png")
                if (KEYFRAMES / f"{s['id']}.png").exists()
                else sha256_file(SHOTS / f"{s['id']}.mp4")
                if (SHOTS / f"{s['id']}.mp4").exists()
                else None
                for s in self.story.shots
            },
        }
        key = self.cache.key(manifest)
        if not force and out.exists() and self.cache.hit("assemble", key, ".mp4"):
            log_run(
                {
                    "stage": "assemble",
                    "shot_id": None,
                    "model": "ffmpeg",
                    "params": {"aspect": aspect},
                    "seed": None,
                    "latency_s": 0.0,
                    "gpu_minutes": 0.0,
                    "cost_usd": 0.0,
                    "cached": True,
                    "output": str(out),
                }
            )
            return out

        start = time.perf_counter()
        work = ASSEMBLY / f"work_{aspect.replace(':', 'x')}"
        work.mkdir(parents=True, exist_ok=True)

        clips: List[Path] = []
        intro_image = (
            KEYFRAMES / "abba_gebre_hanna_portrait.png"
            if aspect == "16:9"
            else KEYFRAMES / "abba_gebre_hanna_portrait_9x16.png"
        )
        if not intro_image.exists():
            intro_image = KEYFRAMES / "abba_gebre_hanna_portrait.png"
        if intro_image.exists():
            intro_clip = work / "opening_portrait.mp4"
            self._kenburns(
                intro_image,
                w,
                h,
                intro_dur,
                intro_clip,
                "slow camera push in",
            )
            clips.append(intro_clip)

        for i in range(1, 6):
            variant = "9x16" if aspect == "9:16" else "source"
            radio_image = KEYFRAMES / f"communication_0{i}_{variant}.png"
            if radio_image.exists():
                radio_clip = work / f"radio_cut_0{i}.mp4"
                self._kenburns(
                    radio_image,
                    w,
                    h,
                    communication_dur,
                    radio_clip,
                    "slow camera push in",
                )
                clips.append(radio_clip)

        for shot in self.story.shots:
            sid = shot["id"]
            dur = float(timing.get(sid, shot["duration"]))
            clip = work / f"{sid}.mp4"
            video_src = SHOTS / f"{sid}.mp4"
            image_src = KEYFRAMES / f"{sid}.png"

            if image_src.exists():
                self._kenburns(
                    image_src,
                    w,
                    h,
                    dur,
                    clip,
                    shot.get("motion_prompt", ""),
                )
            elif video_src.exists():
                self._normalize_video(video_src, w, h, dur, clip)
            else:
                self._placeholder_image(shot, image_src)
                self._kenburns(
                    image_src,
                    w,
                    h,
                    dur,
                    clip,
                    shot.get("motion_prompt", ""),
                )
            clips.append(clip)

        end_png = self._end_card(w, h, self.story.meta["end_card"]["text"])
        end_clip = work / "end_card.mp4"
        self._end_card_video(end_png, w, h, end_dur, end_clip)
        clips.append(end_clip)

        video_track = work / "video.mp4"
        list_file = work / "video_concat.txt"
        list_file.write_text(
            "\n".join(f"file '{p.resolve().as_posix()}'" for p in clips),
            encoding="utf-8",
        )
        ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_file,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(FPS_DEFAULT),
                video_track,
            ]
        )

        narration_track = work / "narration.wav"
        self._build_narration_track(timing, total, narration_track, intro_total)

        music_src = MUSIC / "score.wav"
        if not music_src.exists():
            ProceduralScore().generate(total + 2.0, music_src)

        mixed = work / "mixed.wav"
        self._mix(narration_track, music_src, total, mixed)

        srt = work / "subtitles.srt"
        self._build_srt(timing, srt)

        ffmpeg(
            [
                "-i",
                video_track,
                "-i",
                mixed,
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                out,
            ]
        )

        latency = time.perf_counter() - start
        self.cache.write_meta("assemble", key, {"aspect": aspect})
        self.cache.path("assemble", key, ".mp4").write_bytes(out.read_bytes())
        log_run(
            {
                "stage": "assemble",
                "shot_id": None,
                "model": "ffmpeg",
                "params": {"aspect": aspect, "width": w, "height": h},
                "seed": None,
                "latency_s": round(latency, 3),
                "gpu_minutes": 0.0,
                "cost_usd": 0.0,
                "cached": False,
                "output": str(out),
            }
        )

        shutil.copy2(srt, FINAL / f"heritage_short_{aspect.replace(':', 'x')}.srt")
        return out


if __name__ == "__main__":
    import argparse
    from .common import CACHE, ROOT, load_timing

    parser = argparse.ArgumentParser(description="Run assembly stage.")
    parser.add_argument("--story", type=Path, default=ROOT / "storyboard.json")
    parser.add_argument("--aspect", choices=["9:16", "16:9", "both"], default="both")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    story = Storyboard(args.story)
    timing = load_timing(story)
    assembler = AssemblyStage(Config.load(), story, Cache(CACHE))
    for a in (["9:16", "16:9"] if args.aspect == "both" else [args.aspect]):
        assembler.run(timing, a, args.force)
