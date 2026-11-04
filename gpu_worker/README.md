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

- **Gemini story planner:** turns a Telugu story into a validated JSON scene plan with visual prompts, camera notes, characters, Telugu dialogue and continuity notes. Requires `GEMINI_API_KEY` in Space Secrets; optionally set `GEMINI_MODEL`. It plans only and does not render scenes.
- **Scene render manifest:** converts the approved plan into per-scene Wan2.2 frame counts/prompts, a shared character-reference filename, and a validated Telugu dialogue script. It is a pre-render package only; it does not launch GPU inference.

- **Telugu voice:** creates a separate MP3 using the online Edge TTS service, with Telugu male (Mohan) and female (Shruti) voices.
- **Character dialogue soundtrack:** accepts speaker-labelled Telugu lines (`Speaker|Voice|Dialogue`), synthesizes each line, inserts short pauses, and joins them into one WAV soundtrack using FFmpeg.
- **Scene stitching:** normalizes 2–12 generated MP4 scenes to a common 24 FPS portrait/landscape/square canvas and joins them into one silent story MP4.
- **Video + dialogue mux:** combines a rendered MP4 with the Telugu WAV/MP3 track; optionally mixes original source audio at a lower volume.
- **New scene:** Wan2.2 TI2V-5B text-to-video or image-to-video runner.
- **Animate / replace character:** Wan2.2 Animate-14B runner using an uploaded driving video and character reference image.
- **Preflight:** validates source files and displays a job manifest.
- **GPU status:** checks whether CUDA hardware is visible.

The Telugu voice and dialogue soundtrack tabs are independent of GPU inference. They need an internet connection and the Edge TTS online service; availability and service behavior may change. The soundtrack builder creates a sequential WAV of dialogue lines. The video + dialogue tab combines that track with a rendered MP4 and can optionally mix the original source audio. Neither feature performs lip-sync.

## Not ready to deploy as a working video generator

The Space still needs:
1. The official Wan2.2 source repository and compatible Python dependencies.
2. The TI2V-5B and/or Animate-14B model checkpoints stored or mounted in the Space.
3. Correct environment paths: `WAN_REPO_PATH`, `WAN_TI2V_CHECKPOINT`, and/or `WAN_ANIMATE_CHECKPOINT`.
4. A compatible GPU allocation with sufficient free VRAM and runtime.

No model weights are downloaded automatically. Do not enable paid hardware or credits without explicit approval. A visible GPU does not prove that a specific model will load or finish.

## Known limitations

- The current TI2V test is deliberately short (41 frames, about 1.7 seconds at 24 FPS), not a full 10-second story. The Gemini planner can draft a multi-scene plan, and the scene render manifest prepares individual render jobs and the dialogue script. Automatic multi-scene GPU rendering is not yet connected.
- Wan2.2 TI2V/Animate models generate silent video; they do not create Telugu dialogue audio.
- Telugu TTS can create separate MP3 lines and a combined WAV dialogue track; the separate mux tab can add the soundtrack to MP4. Accurate Telugu lip-sync and sound effects are not implemented. Basic scene stitching is implemented, but automatic scene selection, transition effects, and story continuity checks are not.
- The source-video preflight tab does not itself render a video; use the dedicated generation tabs when model configuration is complete.

## Lip-sync candidate evaluation

MuseTalk is a possible next experiment: its upstream README states MIT licensing for code and commercial use for its trained model, but lists Chinese, English and Japanese audio examples rather than Telugu. It edits a 256×256 face region and documents identity-detail loss and frame jitter. It may not reliably detect or preserve stylized 3D CGI faces, moustaches or PJ Babu/Yamudu designs. A Telugu test clip is required before integration. Its additional model dependencies have separate license terms. Wav2Lip is not selected because upstream restricts use to personal/research/non-commercial purposes.

## Validation

The GitHub Actions workflow compiles the Python modules and runs unit tests. Passing CI checks verifies code syntax and adapter tests only; it does not verify GPU inference or rendered video.

No access tokens or secrets belong in this repository.
