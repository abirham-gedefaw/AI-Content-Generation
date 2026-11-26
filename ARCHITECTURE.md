# Architecture

## Contract

`storyboard.json` is validated against `schema/storyboard.schema.json` before
any stage runs. It contains the title, language, style block, character
description, narration voice/style, music brief and an ordered list of shots.
Each shot has an id, duration, keyframe prompt, motion prompt, narration line,
reason, seed and optional music cue.

## Stages

1. **narration** — Gemini 3.8 Flash TTS, one WAV per shot. Measures duration
   and writes `outputs/timing.json`. Line-by-line generation makes re-takes
   cheap and keeps subtitles aligned.
2. **keyframes** — first a character reference sheet, then one still per shot.
   Every prompt includes the fixed style block and character description to
   reduce identity drift. Square 1024×1024 keyframes are composed with safe
   margins so the same still crops cleanly to 9:16 and 16:9.
3. **shots** — Wan 2.2 TI2V-5B image-to-video on a local GPU or Kaggle.
   If Wan is unavailable, FFmpeg `zoompan` produces a slow Ken Burns move from
   the keyframe. The fallback is deterministic and free.
4. **music** — ACE-Step 1.5 generates candidates; the first successful track
   is used. A small procedural score is the fallback. The score is instrumental
   so it does not compete with the narrator.
5. **assemble** — FFmpeg normalises every shot to the target aspect and exact
   duration, concatenates, pads narration to picture, mixes music through a
   sidechain compressor, normalises to about −14 LUFS, burns subtitles, adds the
   end card, and exports both ratios.

## Caching

`Cache.key()` hashes the stage's inputs with SHA-256. `Cache.hit()` checks the
output file and a sidecar `.json` containing the same key. A hit is logged with
`cached: true` and costs nothing. Upstream file hashes are included, so changing
a keyframe invalidates the shot that depends on it.

## Retries

Every hosted API call uses `@retry(attempts=3, base_delay=2.0)` with exponential
backoff. Wan and ACE-Step are local subprocesses; their failures fall through to
the stage fallback rather than crashing the film.

## Failure handling

A stage catches per-shot exceptions, logs a `fallback: true` line in
`runs.jsonl`, writes a deterministic substitute, and continues. `ALLOW_FALLBACKS=false`
turns this into strict mode. This design keeps the pipeline honest: the logs
show exactly which calls succeeded and which did not.

## Measurement

Every line in `runs.jsonl` includes model, parameters, seed, latency, GPU
minutes (estimated from wall time for local GPU stages), cost (0 for free tiers)
and output path. `COSTS.md` summarises the measured numbers and a list-price
equivalent.

## Aspect handling

Keyframes are square with a centred subject. Assembly crops to 9:16 or 16:9
from the same source, so a single generation serves both deliverables. Subtitles
use a larger bottom margin and slightly smaller font in vertical.
