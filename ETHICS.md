# Ethics, consent and licences

## Consent record

If a real person’s face, likeness or voice appears, record their informed
consent here **before** generating anything of them.

| Person | Relationship | Scope | Date | Evidence |
|---|---|---|---|---|
| _Example: Grandmother_ | _Story subject_ | _Likeness and voice for this film; words approved_ | _2026-11-20_ | _Recorded voice note / signed note_ |

The pipeline refuses to run if `meta.consent.required` is `true` and
`meta.consent.recorded` is `false`. The sample storyboard ships with
`required: false` because it is a template. Change it when you use a real
person’s story.

## Words in a real person’s mouth

Gemini TTS can replicate a voice. If a real person is voiced, the words must
be ones they have read and agreed to. Record the approved script in this file
or link to it.

## Labelling

- The film ends with a visible card: “Made with AI — a heritage short”.
- When posting, switch on the platform’s AI-content label (YouTube, TikTok,
  Meta).
- Keep any SynthID / C2PA provenance metadata intact.
- Do not remove watermarks from generated files.

## Licences

| Component | Licence / terms | Notes |
|---|---|---|
| Gemini 3.8 Flash TTS | Google Gemini API terms | Free tier; check data-use terms |
| Cloudflare Workers AI FLUX.1 schnell | Black Forest Labs terms via Cloudflare | Daily free allowance |
| FLUX.2 klein 4B | Apache 2.0 (4B); larger 9B is non-commercial | Check the model card you use |
| Wan 2.2 TI2V-5B | Apache 2.0 | Outputs usable commercially |
| ACE-Step 1.5 | MIT | Outputs usable commercially |
| FFmpeg | LGPL / GPL depending on build | Assembly only |
| Code in this repository | MIT | — |

## Private data

Free endpoints may use inputs to improve their models. Do not send private
family details, addresses, or identifiable images of people who have not
consented. For private stories, prefer local Wan and ACE-Step, and keep the
narration text free of sensitive specifics.
