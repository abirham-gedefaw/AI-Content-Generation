# Kaggle / Colab GPU Guide (Wan 2.2 TI2V-5B & ACE-Step 1.5)

Use this guide when running the heavy open-weight GPU stages on Kaggle (2x T4, ~30 GPU hours/week free with phone verification) or Google Colab.

## 1. Wan 2.2 TI2V-5B (Moving Shots)

```bash
git clone https://github.com/Wan-Video/Wan2.2.git
cd Wan2.2
pip install -r requirements.txt
# Download Wan2.2-TI2V-5B weights (Apache 2.0) via huggingface-cli
huggingface-cli download Wan-AI/Wan2.2-TI2V-5B --local-dir ./Wan2.2-TI2V-5B
```

Set in `.env`:
```env
WAN_DIR=/path/to/Wan2.2
WAN_CKPT_DIR=/path/to/Wan2.2/Wan2.2-TI2V-5B
```

Tips for 16 GB T4:
- Always keep `--offload_model True --convert_model_dtype --t5_cpu`.
- Draft at `480p` first, batch jobs, and reserve Wan for character/emotion shots while using FFmpeg Ken Burns for inserts.

## 2. ACE-Step 1.5 (Original Score)

```bash
git clone https://github.com/ACE-Step/ACE-Step-1.5.git
cd ACE-Step-1.5
pip install -e .
```

Set in `.env`:
```env
ACESTEP_DIR=/path/to/ACE-Step-1.5
ACESTEP_CONFIG=acestep-v15-turbo
ACESTEP_LM=acestep-5Hz-lm-0.6B
```
