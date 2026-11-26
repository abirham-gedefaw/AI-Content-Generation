Heritage Short Studio

This archive was reconstructed from the project specification supplied in the chat.
Quick start:
  1. Create a virtual environment and install requirements.txt.
  2. Copy .env.example to .env and add your API credentials as needed.
  3. Run: python heritage_studio.py validate --story storyboard.json
  4. Run: python heritage_studio.py run --story storyboard.json --aspect both

FFmpeg must be installed separately. Wan 2.2 and ACE-Step are optional local backends;
the project includes FFmpeg/procedural fallbacks. Review ETHICS.md before using real
people's likenesses or voices.
