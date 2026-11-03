"""Gradio preflight UI for a future Hugging Face ZeroGPU worker.

This is intentionally NOT a video renderer yet. It validates inputs and can
report allocated GPU hardware; it never claims to generate an MP4.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import gradio as gr

try:
    import spaces
except ImportError:  # local CPU development
    class _SpacesFallback:
        @staticmethod
        def GPU(*args, **kwargs):
            def decorate(fn):
                return fn
            return decorate
    spaces = _SpacesFallback()


def _file_info(path: str | None, label: str) -> dict:
    if not path:
        raise gr.Error(f"{label}: ఫైల్ ఇవ్వలేదు.")
    p = Path(path)
    if not p.is_file():
        raise gr.Error(f"{label}: ఫైల్ చదవలేకపోయాం.")
    size = p.stat().st_size
    if size <= 0:
        raise gr.Error(f"{label}: ఫైల్ ఖాళీగా ఉంది.")
    return {"name": p.name, "bytes": size}


def prepare_job(video_path, reference_path, story_te, mode, aspect_ratio):
    if not (story_te or "").strip():
        raise gr.Error("కథను తెలుగులో రాయండి.")
    video = _file_info(video_path, "మూల వీడియో")
    reference = _file_info(reference_path, "క్యారెక్టర్ ఫోటో")
    if video["bytes"] > 100 * 1024 * 1024:
        raise gr.Error("మూల వీడియో 100 MB కంటే పెద్దది.")
    if reference["bytes"] > 20 * 1024 * 1024:
        raise gr.Error("క్యారెక్టర్ ఫోటో 20 MB కంటే పెద్దది.")

    manifest = {
        "schema_version": 1,
        "source_video": video,
        "character_reference": reference,
        "story_prompt_te": story_te.strip(),
        "mode": mode,
        "aspect_ratio": aspect_ratio,
        "status": "preflight_passed_waiting_for_model_integration",
        "rendered_mp4": False,
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2), (
        "ఇన్‌పుట్ తనిఖీ విజయవంతం. ఇది ఇంకా వీడియో రెండర్ చేయలేదు. "
        "Wan2.2 మోడల్ వెయిట్స్, preprocess మరియు inference కనెక్షన్ తదుపరి దశ."
    )


@spaces.GPU(duration=30)
def inspect_gpu():
    try:
        import torch
    except Exception as exc:
        return f"PyTorch అందుబాటులో లేదు: {type(exc).__name__}: {exc}"
    if not torch.cuda.is_available():
        return "GPU allocation కనిపించలేదు. ZeroGPU hardware సెట్టింగ్ / queue తనిఖీ చేయాలి."
    props = torch.cuda.get_device_properties(0)
    total_gib = props.total_memory / (1024 ** 3)
    free_gib = torch.cuda.mem_get_info(0)[0] / (1024 ** 3)
    return (
        f"GPU: {props.name}\n"
        f"VRAM మొత్తం: {total_gib:.1f} GiB\n"
        f"ప్రస్తుతం ఖాళీ VRAM: {free_gib:.1f} GiB\n"
        "గమనిక: GPU కనిపించడం మాత్రమే Wan2.2 మోడల్ లోడ్ అవుతుందని నిర్ధారణ కాదు."
    )


with gr.Blocks(title="Macherla Guru — AI Video GPU Worker") as demo:
    gr.Markdown(
        "# 🎬 Macherla Guru — GPU Worker (Preflight)\n"
        "తెలుగు కథ + వీడియో + క్యారెక్టర్ రిఫరెన్స్. "
        "**ఇది ప్రస్తుతం input/GPU readiness పరీక్ష మాత్రమే; MP4 జనరేషన్ ఇంకా కనెక్ట్ కాలేదు.**"
    )
    with gr.Row():
        video = gr.Video(label="మూల వీడియో", sources=["upload"])
        reference = gr.Image(label="క్యారెక్టర్ రిఫరెన్స్", type="filepath")
    story = gr.Textbox(label="కథ / సూచన (తెలుగులో)", lines=5)
    mode = gr.Radio(
        choices=[
            "animate_reference",
            "replace_character",
            "story_driven_new_scenes",
        ],
        value="animate_reference",
        label="పని రకం",
    )
    ratio = gr.Radio(choices=["9:16", "16:9", "1:1"], value="9:16", label="Aspect ratio")
    prepare = gr.Button("ఇన్‌పుట్‌లను తనిఖీ చేయి", variant="primary")
    manifest = gr.Code(label="Job manifest", language="json")
    status = gr.Textbox(label="స్థితి")
    prepare.click(prepare_job, [video, reference, story, mode, ratio], [manifest, status])

    gr.Markdown("## GPU availability check")
    gpu_button = gr.Button("GPU ఉందో తనిఖీ చేయి")
    gpu_result = gr.Textbox(label="GPU సమాచారం", lines=4)
    gpu_button.click(inspect_gpu, outputs=gpu_result)

    gr.Markdown(
        "### ఇంకా కనెక్ట్ చేయాల్సినవి\n"
        "- Wan2.2-Animate-14B model weights + official preprocessing/inference scripts\n"
        "- Story-driven text/image-to-video stage\n"
        "- Telugu TTS / recorded dialogue + lip-sync + final MP4 muxing"
    )


if __name__ == "__main__":
    demo.queue(max_size=4).launch()
