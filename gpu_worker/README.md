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

- **Telugu voice:** creates a separate MP3 using the online Edge TTS service, with Telugu male (Mohan) and female (Shruti) voices.\n- **Character dialogue soundtrack:** accepts speaker-labelled Telugu lines (`Speaker|Voice|Dialogue`), synthesizes each line, inserts short pauses, and joins them into one WAV soundtrack using FFmpeg.
- **Video + dialogue mux:** combines a rendered MP4 with the Telugu WAV/MP3 track; optionally mixes original source audio at a lower volume.
- **New scene:** Wan2.2 TI2V-5B text-to-video or image-to-video runner.
- **Animate / replace character:** Wan2.2 Animate-14B runner using an uploaded driving video and character reference image.
- **Preflight:** validates source files and displays a job manifest.
- **GPU status:** checks whether CUDA hardware is visible.

The Telugu voice and dialogue soundtrack tabs are independent of GPU inference. They need an internet connection and the Edge TTS online service; availability and service behavior may change. The soundtrack builder creates a sequential WAV of dialogue lines, but it does not perform lip-sync or mux the audio into a generated video.

## Not ready to deploy as a working video generator

The Space still needs:
1. The official Wan2.2 source repository and compatible Python dependencies.
2. The TI2V-5B and/or Animate-14B model checkpoints stored or mounted in the Space.
3. Correct environment paths: `WAN_REPO_PATH`, `WAN_TI2V_CHECKPOINT`, and/or `WAN_ANIMATE_CHECKPOINT`.
4. A compatible GPU allocation with sufficient free VRAM and runtime.

No model weights are downloaded automatically. Do not enable paid hardware or credits without explicit approval. A visible GPU does not prove that a specific model will load or finish.

## Known limitations

- The current TI2V test is deliberately short (41 frames), not a full 10-second story.
- Wan2.2 TI2V/Animate models generate silent video; they do not create Telugu dialogue audio.
- Telugu TTS can create separate MP3 lines and a combined WAV dialogue track; a separate mux step can add the soundtrack to MP4. Accurate Telugu lip-sync, scene stitching, and sound effects are not implemented.
- The source-video preflight tab does not itself render a video; use the dedicated generation tabs when model configuration is complete.

## Validation

The GitHub Actions workflow compiles the Python modules and runs unit tests. Passing CI checks verifies code syntax and adapter tests only; it does not verify GPU inference or rendered video.

No access tokens or secrets belong in this repository.
