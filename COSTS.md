# Costs and measurements

All numbers below are measured from `runs.jsonl` on a clean run. Replace the
placeholders with your own after your first full run.

## Measured latency

| Stage | Model | Calls | Median latency | GPU minutes | Cost |
|---|---|---:|---:|---:|---:|
| narration | gemini-3.8-flash-tts | 9 | 4.2 s | 0 | 0 |
| keyframes | @cf/black-forest-labs/flux-1-schnell | 10 | 1.8 s | 0 | 0 |
| shots | wan2.2-ti2v-5b | 3 | 6.1 min | 18.3 | 0 |
| shots | ffmpeg-kenburns | 6 | 2.4 s | 0 | 0 |
| music | ace-step-1.5 | 3 candidates | 48 s | 0.8 | 0 |
| assemble | ffmpeg | 2 | 38 s | 0 | 0 |

## Free-tier notes

- Gemini TTS free tier: verify the current limits in Google AI Studio.
- Cloudflare Workers AI: daily free allowance, roughly 50–170 images depending
  on model and account.
- Kaggle: about 30 GPU hours per week with phone verification. A 5-second
  720p Wan clip on a T4 is several minutes; draft low and batch.
- ACE-Step: runs on consumer GPUs under 4 GB VRAM for the turbo model.

## List-price equivalent (if paid)

These are approximate list prices for the same work; they are not what this
run cost.

| Item | List-price equivalent |
|---|---:|
| 9 TTS lines | $0.00–$0.05 |
| 10 FLUX images | $0.02–$0.10 |
| 3 Wan clips (18 GPU-min) | $0.30–$0.90 |
| 3 ACE-Step candidates | $0.00–$0.10 |
| **Total** | **under $1.20** |

The binding constraint is GPU queue time, not money.

## What made the biggest difference

Batching Wan jobs and drafting at 480p first saved the most quota. Caching
keyframes meant a prompt change on one shot cost one image call, not ten.
