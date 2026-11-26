# Short Commands Cheat Sheet

## Windows PowerShell (`.\studio.ps1`)

| Command | What it does |
|---|---|
| `.\studio.ps1 setup` | Create `.venv` and install packages |
| `.\studio.ps1 smoke` | Check keys, FFmpeg, and log to `runs.jsonl` |
| `.\studio.ps1 validate` | Validate `storyboard.json` against schema |
| `.\studio.ps1 radio` | Build Phase 1 radio cut (`outputs/final/radio_cut_9x16.mp4`) |
| `.\studio.ps1 film` | Run full pipeline & export `9:16` + `16:9` |
| `.\studio.ps1 regen s03` | Regenerate shot `s03` keyframes and re-assemble |
| `.\studio.ps1 test` | Run unit tests (`pytest -v`) |
| `.\studio.ps1 clean` | Delete `outputs/` and `runs.jsonl` |

## Direct Python CLI (any OS, with `.venv` active)

```bash
python heritage_studio.py smoke
python heritage_studio.py validate
python heritage_studio.py radio
python heritage_studio.py run
python heritage_studio.py regen --stage keyframes --shot s03
```

## Linux / macOS (`make`)

```bash
make install
make smoke
make validate
make radio
make film
make regen SHOT=s03
make test
```

## Outputs
- `outputs/final/heritage_short_9x16.mp4`
- `outputs/final/heritage_short_16x9.mp4`
- `outputs/final/heritage_short_9x16.srt`
- `outputs/final/heritage_short_16x9.srt`
- `outputs/final/radio_cut_9x16.mp4`
