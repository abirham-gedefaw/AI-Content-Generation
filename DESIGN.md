# Design

## Audience

**Primary audience:** family members in Dessie and the Ethiopian diaspora,
aged 18–45, watching on a phone, often in a quiet moment at home. They know the
story’s world but may not have heard this particular telling.

**Where they watch:** WhatsApp, TikTok, Instagram Reels, YouTube Shorts — mostly
vertical, often with sound on but sometimes silent with subtitles.

## Intent

At the end, the audience should feel the quiet dignity of an ordinary walk and
recognise something of their own grandmother in it. They should understand that
the story is not the market; it is the care in the routine.

## Constraints

- 60–90 seconds.
- Narration in Amharic, subtitles in English.
- No paid API, no consent risk, no identifiable private family details in a
  free endpoint that may train on inputs.
- Must export both vertical and horizontal from the same material.

## Shot reasons

Every shot in `storyboard.json` carries a `reason` field. If a shot cannot be
justified in one sentence, it is cut.

## User test 1 — radio cut

**When:** before any pictures were generated.
**Who:** three people from the intended audience (two family members, one
diaspora friend).
**What they heard:** narration over a placeholder score on a black screen.

| What we asked | What they said | What changed |
|---|---|---|
| Where did you lose attention? | “The opening felt slow before she left the house.” | Merged the original two establishing shots into one 7-second shot. |
| Which line felt most like her? | “The line about the stones — I could hear her voice.” | Kept the stones insert and gave it 0.5 s more. |
| Did the ending land? | “I wanted to see her home, not just walking.” | Added the return shot at golden hour. |
| Was the narration too fast? | “Slightly fast on the second line.” | Regenerated that line with a slower style instruction. |

The radio cut changed the storyboard: 10 shots became 9, the opening tightened,
and the return shot was added.

## User test 2 — near-final cut

**When:** after keyframes, shots and score, before final loudness pass.
**Who:** three people from the audience, including one who had not seen the
radio cut.

| What we asked | What they said | What changed |
|---|---|---|
| Could you follow the story without subtitles? | “Yes, but the market arrival was a little sudden.” | Added 0.4 s of held stillness at the market entrance before the pan. |
| Did the music ever fight the voice? | “Only in the middle — the flute was loud.” | Lowered music bed from 0.35 to 0.30 and increased ducking release. |
| Did the vertical crop lose anything important? | “The basket was cut off in the walking shot.” | Re-centred the keyframe prompt and regenerated `s03` only. |
| Would you send it to someone? | “Yes — to my mother.” | Kept the end card short so it does not delay sharing. |

The near-final test changed the mix and one keyframe; only `s03` was
regenerated, which the cache logs as a single new model call.

## What I would test next

- A version with no music, only ambience, to see whether the silence feels
  more intimate.
- A Tigrinya or Afaan Oromo narration for relatives who would share it more
  readily in that language.
