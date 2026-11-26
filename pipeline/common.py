"""Shared configuration, storyboard contract, cache, logging, and FFmpeg helpers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# pyrefly: ignore[missing-import]
from dotenv import load_dotenv
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
KEYFRAMES = OUT / "keyframes"
SHOTS = OUT / "shots"
NARRATION = OUT / "narration"
MUSIC = OUT / "music"
ASSEMBLY = OUT / "assembly"
FINAL = OUT / "final"
CACHE = OUT / "cache"
RUNS = ROOT / "runs.jsonl"
STAGES = ("narration", "keyframes", "shots", "music", "assemble")
FPS_DEFAULT = 24


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    for p in (KEYFRAMES, SHOTS, NARRATION, MUSIC, ASSEMBLY, FINAL, CACHE):
        p.mkdir(parents=True, exist_ok=True)


def sha256_json(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:20]


def log_run(entry: Dict[str, Any]) -> None:
    entry = {"ts": utc_now(), **entry}
    with RUNS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def retry(attempts: int = 3, base_delay: float = 2.0):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            last = None
            for i in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    if i == attempts:
                        break
                    delay = base_delay * (2 ** (i - 1))
                    print(f"  ! {fn.__name__} failed ({exc}); retrying in {delay:.1f}s")
                    time.sleep(delay)
            raise last  # type: ignore[misc]

        return wrapper

    return decorator


def resolve_ffmpeg() -> str:
    env_bin = os.getenv("FFMPEG_BIN", "").strip()
    if env_bin:
        return env_bin
    which_bin = shutil.which("ffmpeg")
    if which_bin:
        return which_bin
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def resolve_ffprobe() -> str:
    env_bin = os.getenv("FFPROBE_BIN", "").strip()
    if env_bin:
        return env_bin
    which_bin = shutil.which("ffprobe")
    if which_bin:
        return which_bin
    return "ffprobe"


def ffmpeg(args: List[Any], timeout: int = 1800) -> None:
    cmd = [resolve_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error"] + [str(a) for a in args]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{' '.join(cmd)}\n{proc.stderr[-2000:]}")


def ffprobe_duration(path: Path) -> float:
    probe = resolve_ffprobe()
    if shutil.which(probe) or Path(probe).exists():
        out = subprocess.check_output(
            [
                probe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            text=True,
        )
        return float(out.strip())
    # Fallback for WAV files when ffprobe is not installed alongside imageio-ffmpeg
    if path.suffix.lower() == ".wav":
        import wave

        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    raise RuntimeError(f"ffprobe not found to measure {path}")


def silence_wav(path: Path, duration: float, sr: int = 48000) -> None:
    duration = max(0.05, float(duration))
    ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={sr}:cl=mono",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "pcm_s16le",
            path,
        ]
    )


def pad_wav(src: Path, dst: Path, target_duration: float) -> None:
    ffmpeg(
        [
            "-i",
            src,
            "-af",
            f"apad=whole_dur={target_duration:.3f}",
            "-t",
            f"{target_duration:.3f}",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            dst,
        ]
    )


def clean_narration_wav(src: Path, dst: Path) -> None:
    """Reduce hiss and low-frequency muddiness while preserving spoken detail."""
    ffmpeg(
        [
            "-i",
            src,
            "-af",
            "afftdn=nf=-25,"
            "highpass=f=70,"
            "lowpass=f=12000,"
            "silenceremove=start_periods=1:start_duration=0.08:start_threshold=-38dB,"
            "acompressor=threshold=0.08:ratio=2.5:attack=5:release=60,"
            "alimiter=limit=0.95,"
            "loudnorm=I=-16:TP=-1.5:LRA=7,"
            "afade=t=in:st=0:d=0.015",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            dst,
        ]
    )


def wrap_for_subtitle(text: str, width: int = 42) -> List[str]:
    if not text.strip():
        return []
    lines: List[str] = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph.strip(), width=width) or [""])
    return lines[:2]


def srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


@dataclass
class Config:
    gemini_api_key: str = ""
    cf_account_id: str = ""
    cf_api_token: str = ""
    cf_flux_model: str = "@cf/black-forest-labs/flux-1-schnell"
    wan_dir: str = ""
    wan_ckpt_dir: str = ""
    acestep_dir: str = ""
    acestep_config: str = "acestep-v15-turbo"
    acestep_lm: str = "acestep-5Hz-lm-0.6B"
    allow_fallbacks: bool = True

    @classmethod
    def load(cls) -> "Config":
        load_dotenv(ROOT / ".env")
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            cf_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
            cf_api_token=os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
            cf_flux_model=os.getenv(
                "CF_FLUX_MODEL", "@cf/black-forest-labs/flux-1-schnell"
            ).strip(),
            wan_dir=os.getenv("WAN_DIR", "").strip(),
            wan_ckpt_dir=os.getenv("WAN_CKPT_DIR", "").strip(),
            acestep_dir=os.getenv("ACESTEP_DIR", "").strip(),
            acestep_config=os.getenv("ACESTEP_CONFIG", "acestep-v15-turbo").strip(),
            acestep_lm=os.getenv("ACESTEP_LM", "acestep-5Hz-lm-0.6B").strip(),
            allow_fallbacks=os.getenv("ALLOW_FALLBACKS", "true").lower() != "false",
        )


class Storyboard:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.schema = json.loads(
            (ROOT / "schema" / "storyboard.schema.json").read_text(encoding="utf-8")
        )
        self.validate()

    def validate(self) -> None:
        validator = Draft7Validator(self.schema)
        errors = sorted(validator.iter_errors(self.data), key=lambda e: list(e.path))
        if errors:
            messages = "\n".join(f"  - {e.message} at {list(e.path)}" for e in errors)
            raise SystemExit(f"storyboard.json is invalid:\n{messages}")

        ids = [s["id"] for s in self.data["shots"]]
        if len(ids) != len(set(ids)):
            raise SystemExit("storyboard.json: shot ids must be unique")

        consent = self.data["meta"].get("consent", {})
        if consent.get("required") and not consent.get("recorded"):
            raise SystemExit(
                "Consent is required but not recorded in meta.consent. "
                "Record consent in ETHICS.md and set meta.consent.recorded=true before generating."
            )

    @property
    def meta(self) -> Dict[str, Any]:
        return self.data["meta"]

    @property
    def shots(self) -> List[Dict[str, Any]]:
        return self.data["shots"]

    @property
    def style_block(self) -> str:
        return self.data.get("style_block", "")

    @property
    def character(self) -> Dict[str, Any]:
        return self.data.get("character", {})

    @property
    def narration_cfg(self) -> Dict[str, Any]:
        return self.data.get("narration", {})

    @property
    def music_cfg(self) -> Dict[str, Any]:
        return self.data.get("music", {})

    def shot(self, shot_id: str) -> Dict[str, Any]:
        for s in self.shots:
            if s["id"] == shot_id:
                return s
        raise KeyError(shot_id)


class Cache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def key(self, payload: Any) -> str:
        return sha256_json(payload)

    def path(self, stage: str, key: str, ext: str) -> Path:
        d = self.root / stage
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{key}{ext}"

    def meta_path(self, stage: str, key: str) -> Path:
        return self.path(stage, key, ".json")

    def hit(self, stage: str, key: str, ext: str) -> bool:
        p = self.path(stage, key, ext)
        m = self.meta_path(stage, key)
        if not p.exists() or not m.exists():
            return False
        try:
            meta = json.loads(m.read_text(encoding="utf-8"))
            return meta.get("key") == key
        except Exception:
            return False

    def write_meta(self, stage: str, key: str, meta: Dict[str, Any]) -> None:
        self.meta_path(stage, key).write_text(
            json.dumps({"key": key, **meta}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_timing(story: Storyboard) -> Dict[str, float]:
    p = OUT / "timing.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {s["id"]: float(s["duration"]) for s in story.shots}
