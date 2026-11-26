# Heritage Short Studio

A reproducible, multi-model pipeline for a **60–90 second** heritage short film.  
One file, [`storyboard.json`](storyboard.json), is the contract. Modular stage scripts in `pipeline/` read it and write only their own outputs. Every model call is logged to `runs.jsonl`.

The repository ships with a complete **Amharic sample story** (*The Road to Dessie*, 9 shots, Amharic narration + English subtitles) in [`storyboard.json`](storyboard.json) (and backed up in [`samples/sample_storyboard.json`](samples/sample_storyboard.json)) so you can test the entire pipeline immediately—with or without API keys—and swap in your own story and keys later.

---

## Step-by-Step: How to Run and Generate

### Step 1: Set up the Python environment
```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

pip install -r requirements.txt
```
*(FFmpeg is bundled via `imageio-ffmpeg` in `requirements.txt`, or you can install system FFmpeg.)*

### Step 2: Configure your API keys (optional for dummy run)
```bash
cp .env.example .env
```
Open `.env` and add your free-tier credentials:
- `GEMINI_API_KEY` — from Google AI Studio (used for Gemini 3.8 Flash TTS narration & Flash-Lite subtitle translation).
- `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` — from Cloudflare Workers AI (used for FLUX keyframes).
- `WAN_DIR` / `WAN_CKPT_DIR` — optional local/Kaggle Wan 2.2 TI2V-5B paths (see [`notebooks/kaggle_wan_acestep.md`](notebooks/kaggle_wan_acestep.md)).
- `ACESTEP_DIR` — optional local/Kaggle ACE-Step 1.5 path.

> **Note:** If keys are left blank, the pipeline automatically uses deterministic fallbacks (silence/placeholder stills/Ken Burns motion/procedural ambient score) so you can always verify the full edit end-to-end. Set `ALLOW_FALLBACKS=false` in `.env` for strict production runs.

### Step 3: Smoke test & validate the storyboard
```bash
python heritage_studio.py smoke-test
python heritage_studio.py validate --story storyboard.json
```

### Step 4: Phase 1 — Generate the Radio Cut (prototype)
Test pacing and Amharic narration timing over placeholder music on a black screen before generating images:
```bash
python heritage_studio.py radio-cut --story storyboard.json
```
Output: `outputs/final/radio_cut_9x16.mp4`

### Step 5: Generate the full film (both 9:16 and 16:9)
```bash
python heritage_studio.py run --story storyboard.json --aspect both
```
*(Or run `make film` on Linux/macOS.)*

This runs all stages in order:
1. **`script`** — translates any missing English `subtitle` lines from `narration` (if `GEMINI_API_KEY` is set).
2. **`narration`** — generates per-shot WAVs in `outputs/narration/` and writes `outputs/timing.json`.
3. **`keyframes`** — generates character reference `outputs/keyframes/_reference.png` and per-shot stills in `outputs/keyframes/`.
4. **`shots`** — animates keyframes via Wan 2.2 TI2V-5B or FFmpeg Ken Burns into `outputs/shots/`.
5. **`music`** — generates score via ACE-Step 1.5 or procedural ambient score into `outputs/music/score.wav`.
6. **`assemble`** — pads narration, ducks music (`sidechaincompress`), normalises to `-14 LUFS`, burns English subtitles, appends the `"Made with AI"` end card, and exports both aspect ratios.

Final outputs are written to `outputs/final/`:
- `outputs/final/heritage_short_9x16.mp4`
- `outputs/final/heritage_short_16x9.mp4`
- `outputs/final/heritage_short_9x16.srt`
- `outputs/final/heritage_short_16x9.srt`

### Step 6: Replace with your own story & regenerate single shots
1. Edit [`storyboard.json`](storyboard.json) (keep `samples/sample_storyboard.json` as reference).
2. If a real person's face or voice appears, record consent in [`ETHICS.md`](ETHICS.md) and set `meta.consent.required = true` and `meta.consent.recorded = true`.
3. To change just one shot (e.g. `s03`) and regenerate only that shot:
```bash
python heritage_studio.py regen --story storyboard.json --stage keyframes --shot s03
python heritage_studio.py run --story storyboard.json --aspect both
```
Unchanged stages/shots hit `outputs/cache/` (`cached: true` in `runs.jsonl`) and are skipped.

### Step 7: Run unit tests
```bash
pytest -v
```

---

## Repository structure

```text
heritage-short/
├── heritage_studio.py           # Unified CLI (validate, run, regen, radio-cut, smoke-test)
├── storyboard.json              # Active Amharic sample storyboard (contract between stages)
├── schema/
│   └── storyboard.schema.json   # JSON Schema validated before every run
├── pipeline/
│   ├── common.py                # Config, Storyboard, Cache, FFmpeg helpers, runs.jsonl logger
│   ├── script.py                # Stage 0: Gemini 3.8 Flash-Lite subtitle translation
│   ├── narration.py             # Stage 1: Gemini 3.8 Flash TTS narration
│   ├── keyframes.py             # Stage 2: Cloudflare FLUX character sheet + keyframes
│   ├── shots.py                 # Stage 3: Wan 2.2 TI2V-5B / FFmpeg Ken Burns
│   ├── music.py                 # Stage 4: ACE-Step 1.5 / procedural ambient score
│   └── assemble.py              # Stage 5: FFmpeg mix, ducking, loudness, subtitles, export
├── samples/
│   └── sample_storyboard.json   # Backup copy of the Amharic sample story
├── notebooks/
│   └── kaggle_wan_acestep.md    # Free GPU setup guide for Wan 2.2 and ACE-Step 1.5
├── tests/
│   └── test_pipeline.py         # Unit tests for schema, consent gate, cache, and SRTs
├── outputs/                     # Generated artifacts (keyframes, shots, narration, music, final)
├── runs.jsonl                   # Append-only log of every model/stage call
├── DESIGN.md                    # Audience, intent, and two user-test logs
├── ARCHITECTURE.md              # Stage contracts, caching, retries, failure handling
├── EXPERIMENTS.md               # Hypothesis -> change -> result experiment log
├── FAILURES.md                  # Blockers encountered and fixes/workarounds
├── COSTS.md                     # Measured latency, GPU minutes, and list-price equivalent
├── ETHICS.md                    # Consent record, model licences, AI labelling plan
└── REPORT.md                    # Written project report
```

---

## What it costs

| Stage | Model | Free access | Fallback |
|---|---|---|---|
| Script / translation | Gemini 3.8 Flash-Lite | Free tier | Existing storyboard subtitles |
| Narration | Gemini 3.8 Flash TTS | Free tier, 130+ languages | Silence |
| Keyframes | Cloudflare FLUX.1 schnell / FLUX.2 klein | Daily free allowance | Labelled placeholder still |
| Moving shots | Wan 2.2 TI2V-5B | Kaggle free GPU | FFmpeg Ken Burns |
| Music | ACE-Step 1.5 | Open weights, local GPU | Procedural ambient score |
| Assembly | FFmpeg | Free | — |

## Licence

Code: MIT. Model outputs: see [`ETHICS.md`](ETHICS.md).
