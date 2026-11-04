# AI Video Transformation Prototype — Technical Plan

## Goal
A prompt-driven Telugu workflow for Macherla Guru videos: upload a short raw video, upload a character reference image, describe the new Telugu scene and dialogue, then generate a transformed MP4 with consistent character appearance, expressions, camera language, Telugu voice and lip-sync.

## What is implemented in this branch
- An isolated Streamlit page at pages/3_AI_Video_Transformation.py.
- It collects the source clip, character reference, Telugu story prompt, output aspect ratio and style.
- It creates a ZIP job package with a JSON manifest, SHA-256 integrity hashes and sanitized filenames.
- It clearly reports that a job package is not a rendered MP4.
- A separate Gradio worker prototype contains Wan2.2 TI2V-5B and Animate-14B command adapters, with model weights and GPU paths required through environment configuration.
- Telugu TTS uses Edge TTS online voices (Mohan/Shruti); a speaker-labelled dialogue builder creates a WAV track with configurable pauses.
- A separate FFmpeg mux adapter combines a rendered MP4 and the Telugu dialogue WAV/MP3, optionally mixing source-video audio. Unit tests cover command construction and validation.
- A scene-stitch adapter normalizes 2–12 rendered MP4 clips to a common 24 FPS canvas (9:16, 16:9 or 1:1) and concatenates them into a single silent story MP4.

## Model fit and constraints

### Character animation / replacement
Wan2.2 Animate-14B accepts a driving video and a reference character image. Its documented modes are animation (animate the reference character to follow motion in the driving video) and replacement (replace the character in the driving video). This is the closest open-weight starting point for character continuity. It is not, by itself, a general-purpose system for rewriting every scene from a Telugu story prompt.
Official model card: https://huggingface.co/Wan-AI/Wan2.2-Animate-14B

### New story-driven scenes
A separate text/image-to-video stage is needed to create new locations, actions and shots from the story prompt. Wan2.2 TI2V-5B is a candidate for experiments, but character identity consistency across several generated shots must be tested rather than assumed.

### Telugu dialogue and lip-sync
The animation model does not provide the complete Telugu dialogue pipeline required by this product goal. Telugu TTS and dialogue soundtrack generation are now prototyped, and audio muxing is implemented as a separate FFmpeg step. Accurate lip-sync is still not implemented. MuseTalk is a candidate to test because its project states MIT code licensing and commercial use for its trained model; however its README lists Chinese, English and Japanese as supported audio languages, not Telugu, and describes 256×256 face-region editing. It also warns about identity-detail loss (including moustache/lip details) and frame jitter. Those risks are important for PJ Babu/Yamudu 3D CGI faces, so we must run a Telugu sample on the actual character style before integrating it. Its other model dependencies have separate licenses. Wav2Lip is not selected because its upstream code/weights are restricted to personal/research/non-commercial use.\n\nMuseTalk references: https://github.com/TMElyralab/MuseTalk (README sections Overview and Disclaimer/License). Wav2Lip restriction: https://github.com/Rudrabha/Wav2Lip.

## Free compute reality
Hugging Face ZeroGPU currently supports Gradio Spaces, not Streamlit Spaces. Its published hardware tiers are 48 GB VRAM (large) and 96 GB (xlarge); free personal accounts have a published daily quota of 5 GPU minutes. The current documentation also notes queueing and compatibility limits.

NVIDIA's current support matrix lists Wan2.2-Animate-2-14B with a minimum 80 GB GPU-memory requirement (recommended 4 × 80 GB). A 96 GB ZeroGPU allocation is theoretically above the stated minimum, but that does not prove the model will load or finish within the free quota. The worker must be tested on actual hardware before promising free renders.

References:
- https://huggingface.co/docs/hub/main/spaces-zerogpu
- https://docs.nvidia.com/nim/visual-genai/latest/support-matrix.html
- https://huggingface.co/Wan-AI/Wan2.2-Animate-14B

## Implementation sequence
1. Validate job package creation and download.
2. Build a separate Gradio GPU worker (do not add GPU dependencies to the Streamlit app).
3. Test a very short character-animation/replacement clip with the selected model and actual GPU allocation.
4. Add the text/image-to-video scene-generation stage for story-driven shots.
5. Validate Telugu TTS audio quality for the user's two character voices.
6. Evaluate MuseTalk on a short Telugu clip with the actual PJ Babu/Yamudu 3D CGI style; integrate only if language support, face detection, quality and all dependency licenses are acceptable.
7. Stitch generated scenes into a continuous MP4 and validate a real output; transitions and story continuity remain future work.
8. Mux dialogue audio into the stitched MP4 and validate a real output.
9. Connect the Streamlit page to the worker using authenticated job submission and status polling.

## Safety and project boundaries
- Keep the YouTube Manager app.py unchanged.
- Keep all experiments on branch ai-video-transform-prototype until the full workflow is tested.
- Never store API tokens in source files or ZIP job packages.
- Do not claim a rendered video exists unless an actual MP4 was generated and checked.


## Current status — 2026-11-04
- GitHub Actions syntax checks and unit tests pass on the prototype branch after the latest MP4 mux changes.
- This verifies Python code and command-building tests only. It does not prove online TTS service availability, successful GPU model loading, actual video generation, or lip-sync quality.
- Scene stitching code and a Gradio tab are now implemented, with unit tests for normalization commands; real FFmpeg stitching still needs a runtime video test.
- No Hugging Face Space has been created or deployed; no GPU worker has been run; no real AI MP4 render has been produced.
- The main YouTube Manager app.py on main remains unchanged. Do not merge this prototype into main without the user's explicit approval.
