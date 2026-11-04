"""Assemble an isolated Hugging Face Gradio Space bundle from this worker folder."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

SPACE_README = """---
title: Macherla Guru AI Video Worker
emoji: 🎬
colorFrom: purple
colorTo: blue
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
python_version: "3.11"
pinned: false
---

# Macherla Guru AI Video Worker

Experimental Telugu story-to-video worker. It requires a compatible persistent GPU
and operator-provided Wan2.2 TI2V-5B model weights. No weights are downloaded
automatically. Set Space Secrets/Variables: GEMINI_API_KEY (for planning),
WAN_REPO_PATH and WAN_TI2V_CHECKPOINT (for video rendering).

The full-story renderer needs a persistent CUDA GPU. ZeroGPU is only a short,
quota-limited Gradio GPU allocation and is NOT suitable for this multi-scene runner.
Do not select paid hardware or enable billing without the account owner's explicit
approval. This bundle has passed code/unit tests only; real model inference and
Telugu lip-sync are not verified or implemented.

## Create this Space (account owner action required)

1. Sign in at https://huggingface.co and open https://huggingface.co/new-space.
2. Choose a unique Space name, select **Gradio**, and create the Space.
3. Upload the files from this bundle to the Space repository (including app.py,
   all Python modules, requirements.txt and this README.md).
4. For story planning, add GEMINI_API_KEY under Space Settings > Secrets.
5. Do not add billing details, buy credits, or select paid GPU hardware unless
   the account owner has explicitly decided to pay.
6. A ZeroGPU Space may be available to eligible free personal accounts, but its
   daily quota is only 5 GPU minutes and it does not make the full-story runner
   work. Confirm account eligibility in the Space hardware selector.
7. Actual multi-scene Wan2.2 rendering remains blocked until a persistent,
   compatible CUDA GPU and model checkpoints are provided and tested.

Never paste Hugging Face access tokens or Gemini API keys into chat or source files.
"""

def build_bundle(source_dir: str | Path, output_dir: str | Path) -> Path:
    source = Path(source_dir).resolve()
    output = Path(output_dir).resolve()
    if not source.is_dir():
        raise ValueError("GPU worker source directory does not exist.")
    output.mkdir(parents=True, exist_ok=True)
    for existing in output.iterdir():
        if existing.is_dir():
            shutil.rmtree(existing)
        else:
            existing.unlink()
    python_files = sorted(source.glob("*.py"))
    if not python_files or not (source / "app.py").is_file():
        raise ValueError("Worker source must contain app.py and Python modules.")
    for item in python_files:
        shutil.copy2(item, output / item.name)
    requirements = source / "requirements.txt"
    if not requirements.is_file():
        raise ValueError("Worker requirements.txt is missing.")
    shutil.copy2(requirements, output / "requirements.txt")
    (output / "README.md").write_text(SPACE_README, encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an isolated Hugging Face Space source bundle.")
    parser.add_argument("--source", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--output", default="./dist/macherla-guru-hf-space")
    args = parser.parse_args()
    result = build_bundle(args.source, args.output)
    print(f"Space bundle ready: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
