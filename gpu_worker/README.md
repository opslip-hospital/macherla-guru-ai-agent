---
title: Macherla Guru AI Video Worker
emoji: 🎬
colorFrom: purple
colorTo: blue
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
---

# Macherla Guru AI Video Worker

This is an isolated GPU-worker prototype. It is **not deployed and has not rendered a real video yet**. The `app.py` file is the Gradio entry point.

## UI paths

- **New scene:** Wan2.2 TI2V-5B text-to-video or image-to-video runner.
- **Animate / replace character:** Wan2.2 Animate-14B runner using an uploaded driving video and character reference image.
- **Preflight:** validates source files and displays a job manifest.
- **GPU status:** checks whether CUDA hardware is visible.

Both generation paths are connected to guarded runners. They use argument arrays (not shell commands), bounded execution time, and MP4 container validation. The UI currently reserves up to 120 seconds per GPU call; that may be too short for model loading or inference.

## Not ready to deploy as a working generator

The Space still needs:
1. The official Wan2.2 source repository and compatible Python dependencies.
2. The TI2V-5B and/or Animate-14B model checkpoints stored or mounted in the Space.
3. Correct environment paths: `WAN_REPO_PATH`, `WAN_TI2V_CHECKPOINT`, and/or `WAN_ANIMATE_CHECKPOINT`.
4. A compatible GPU allocation with sufficient free VRAM and runtime.

No model weights are downloaded automatically. Do not enable paid hardware or credits without explicit approval. A visible GPU does not prove that a specific model will load or finish.

## Known limitations

- The current TI2V test is deliberately short (41 frames), not a full 10-second story.
- Wan2.2 TI2V/Animate models generate silent video; they do not create Telugu dialogue audio.
- Telugu TTS or recorded dialogue, accurate Telugu lip-sync, scene stitching, sound effects, and final audio mixing are not implemented.
- The source-video preflight tab does not itself render a video; use the dedicated generation tabs when model configuration is complete.

## Validation

The GitHub Actions workflow compiles the Python modules and runs unit tests. Passing CI checks verifies code syntax and adapter tests only; it does not verify GPU inference or rendered video.

No access tokens or secrets belong in this repository.
