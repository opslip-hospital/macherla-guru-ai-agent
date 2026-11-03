# AI Video Transformation Prototype — Technical Plan

## Goal
A prompt-driven Telugu workflow for Macherla Guru videos: upload a short raw video, upload a character reference image, describe the new Telugu scene and dialogue, then generate a transformed MP4 with consistent character appearance, expressions, camera language, Telugu voice and lip-sync.

## What is implemented in this branch
- An isolated Streamlit page at pages/3_AI_Video_Transformation.py.
- It collects the source clip, character reference, Telugu story prompt, output aspect ratio and style.
- It creates a ZIP job package with a JSON manifest, SHA-256 integrity hashes and sanitized filenames.
- It clearly reports that a job package is not a rendered MP4.

## Model fit and constraints

### Character animation / replacement
Wan2.2 Animate-14B accepts a driving video and a reference character image. Its documented modes are animation (animate the reference character to follow motion in the driving video) and replacement (replace the character in the driving video). This is the closest open-weight starting point for character continuity. It is not, by itself, a general-purpose system for rewriting every scene from a Telugu story prompt.
Official model card: https://huggingface.co/Wan-AI/Wan2.2-Animate-14B

### New story-driven scenes
A separate text/image-to-video stage is needed to create new locations, actions and shots from the story prompt. Wan2.2 TI2V-5B is a candidate for experiments, but character identity consistency across several generated shots must be tested rather than assumed.

### Telugu dialogue and lip-sync
The animation model does not provide the complete Telugu dialogue pipeline required by this product goal. A separate stage is required: Telugu dialogue/script preparation; Telugu TTS voice generation (or user-supplied recorded dialogue); lip-sync / mouth-motion alignment; audio mixing and final MP4 muxing. No Telugu voice or lip-sync generation is implemented in this prototype yet.

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
5. Add Telugu TTS and lip-sync, then mux audio/video and validate the MP4.
6. Connect the Streamlit page to the worker using authenticated job submission and status polling.

## Safety and project boundaries
- Keep the YouTube Manager app.py unchanged.
- Keep all experiments on branch ai-video-transform-prototype until the full workflow is tested.
- Never store API tokens in source files or ZIP job packages.
- Do not claim a rendered video exists unless an actual MP4 was generated and checked.
