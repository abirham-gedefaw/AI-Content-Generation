# Failures and fixes

## Gemini TTS 429 / quota exhausted
**Symptom:** `ResourceExhausted` or HTTP 429 mid-narration.
**Cause:** free-tier rate limit.
**Tried:** retry with backoff (helped for short bursts); reducing request size.
**Fix:** generate line by line, cache each WAV, and re-run only the missing
lines. If quota is gone, the pipeline writes a short silence and continues;
`FAILURES.md` records which lines need a re-run. Strict mode fails loudly.

## Cloudflare FLUX 429 or model unavailable
**Symptom:** `429 Too Many Requests` or `model not found`.
**Cause:** daily free allowance or a model ID that is not enabled.
**Tried:** retry without explicit width/height; switching to
`@cf/black-forest-labs/flux-1-schnell`.
**Fix:** the stage falls back to a labelled placeholder so assembly can
continue. Re-run `regen --stage keyframes` later; cache keeps the shots that
already succeeded.

## Wan 2.2 out of memory on a T4
**Symptom:** CUDA OOM during `generate.py`.
**Cause:** 720p TI2V-5B is tight on a 16 GB T4.
**Tried:** `--offload_model True`, `--convert_model_dtype`, `--t5_cpu`.
**Fix:** draft at 480p or use the Ken Burns fallback for non-critical shots.
Reserve Wan for close-ups and shots where motion matters.

## ACE-Step import or VRAM error
**Symptom:** `ModuleNotFoundError: acestep` or CUDA OOM.
**Cause:** `ACESTEP_DIR` not on `sys.path`, or the 4B XL model needs more VRAM.
**Tried:** `acestep-v15-turbo` instead of XL; `uv sync` in the ACE-Step repo.
**Fix:** use the procedural score fallback and document it. The film still has
an original score.

## FFmpeg `sidechaincompress` error
**Symptom:** “Cannot select sample format” or “channel layout mismatch”.
**Cause:** narration mono, music stereo.
**Fix:** both inputs pass through `aformat=sample_rates=48000:channel_layouts=stereo`
before the compressor. This is now fixed in `_mix()`.

## Subtitles missing or garbled
**Symptom:** no text on screen.
**Cause:** libass not built into FFmpeg, or font name not found.
**Fix:** install a full FFmpeg build with libass; use `DejaVu Sans`, which is
available on most Linux systems. A sidecar `.srt` is always written so the
film can be uploaded with soft subtitles if burn-in fails.

## Character identity drift
**Symptom:** the grandmother’s face changes between shots.
**Cause:** text-only prompts re-describe the character differently each time.
**Fix:** a fixed style block, a reference sheet, and a fixed character
description. If drift persists, lower the motion amount in the Wan prompt;
large motion is where identity breaks first.
