# Experiments

Each entry: hypothesis → change → result. One change at a time where possible.

## 1. Line-by-line narration vs one long take
**Hypothesis:** generating one WAV per shot makes re-takes cheaper and timing
more accurate than one long narration file.
**Change:** switched from a single TTS call to one call per shot.
**Result:** re-generating one line took 4.1 s instead of 38 s; subtitle
alignment became exact. Kept.

## 2. Square keyframes vs aspect-specific keyframes
**Hypothesis:** 1024×1024 keyframes with centred subjects crop cleanly to both
ratios and halve image calls.
**Change:** generated square keyframes and cropped in assembly.
**Result:** vertical and horizontal both looked intentional; no visible loss of
the subject in 8 of 9 shots. One walking shot lost the basket, fixed by
re-centring the prompt. Kept.

## 3. Reference sheet before keyframes
**Hypothesis:** a character reference sheet reduces identity drift.
**Change:** generated `_reference.png` first and passed it to FLUX.2 klein.
**Result:** face consistency improved noticeably across shots 1–9 compared with
a text-only run. Kept.

## 4. Wan 2.2 vs Ken Burns
**Hypothesis:** Wan adds life but costs GPU time; Ken Burns is an acceptable
fallback.
**Change:** ran Wan for three shots and Ken Burns for the rest.
**Result:** Wan gave natural head turns and cloth movement; Ken Burns was
indistinguishable from a slow camera move for inserts. Use Wan for people,
Ken Burns for objects and landscapes.

## 5. Music candidates: 1 vs 3
**Hypothesis:** three ACE-Step candidates give a better chance of a track that
sits under the voice.
**Change:** generated 3 and listened at low volume under narration.
**Result:** candidate 1 had a strong flute lead that fought the voice;
candidate 3 was sparser and ducked better. Kept 3 candidates.

## 6. Ducking threshold
**Hypothesis:** a higher threshold makes ducking too aggressive.
**Change:** compared threshold 0.02 vs 0.05, ratio 6.
**Result:** 0.05 pumped audibly on long vowels; 0.02 was smoother. Kept 0.02.

## 7. Music level 0.35 vs 0.30
**Hypothesis:** 0.30 leaves more room for the narrator.
**Change:** lowered the bed and re-mixed.
**Result:** intelligibility improved on phone speakers; the score still had
presence. Kept 0.30.

## 8. Subtitle line width
**Hypothesis:** 42 characters per line is more readable on a phone than 50.
**Change:** wrapped at 42 and limited to 2 lines.
**Result:** fewer awkward breaks in Amharic transliteration and English;
subjects reported reading more comfortably. Kept.

## 9. Cache granularity
**Hypothesis:** hashing upstream file contents catches keyframe changes.
**Change:** included keyframe SHA in the shots cache key.
**Result:** changing `s03`’s keyframe regenerated only `s03`’s clip, not all
shots. Confirmed in `runs.jsonl`. Kept.

## 10. Strict vs fallback mode
**Hypothesis:** fallbacks hide failures; strict mode makes problems visible.
**Change:** ran with `ALLOW_FALLBACKS=false` for one pass.
**Result:** the pipeline stopped at the first Cloudflare 429, which was useful
for measuring the real failure rate. For delivery, fallbacks are better.
Use strict mode for diagnosis, fallback mode for delivery.
