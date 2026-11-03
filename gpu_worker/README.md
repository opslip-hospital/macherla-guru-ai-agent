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

This Space is a **preflight prototype**, not a video generator yet. The `app.py` file is the Gradio entry point.

It validates a source clip, a character reference image and a Telugu story prompt. Its optional GPU check reports the allocated device and VRAM. It does not download model weights or connect the UI to the renderer yet. An isolated Wan2.2 command runner now exists for a prepared local checkout; it executes preprocessing/inference only when explicitly called, uses a timeout, and verifies the MP4 container. Telugu speech synthesis and lip-sync are not implemented.

## Hardware
For an initial Wan2.2 Animate-14B experiment, the project needs a compatible GPU allocation and enough free VRAM. A GPU being visible is not proof that the model will load. Do not enable paid hardware without explicit approval.

## Next integration steps
1. Add Wan2.2 official preprocessing and inference in an isolated runtime.
2. Test a tiny clip in animation mode.
3. Add character replacement.
4. Add a separate text/image-to-video scene generation stage for story-driven new shots.
5. Add Telugu TTS / recorded dialogue, lip-sync, audio mix and MP4 validation.

No access tokens or secrets belong in this repository.
