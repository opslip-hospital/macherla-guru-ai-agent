"""Gradio UI for the isolated Macherla Guru GPU worker."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import gradio as gr
import spaces

from telugu_tts import TELUGU_VOICES, TeluguTTSSetupError, synthesize_telugu_speech
from dialogue_audio import DialogueAudioError, build_dialogue_soundtrack
from ti2v_adapter import TI2VSetupError, run_ti2v_job
from wan_animate_adapter import WanSetupError, run_wan_animate_job


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
        "ఇది preflight తనిఖీ మాత్రమే; MP4 కోసం పై generation tabs ఉపయోగించండి."
    )


def create_telugu_voice(dialogue, voice_label, rate_label):
    output_dir = Path(tempfile.mkdtemp(prefix="macherla_telugu_voice_"))
    output_file = output_dir / "telugu_dialogue.mp3"
    rates = {
        "నెమ్మదిగా": "-10%",
        "సాధారణం": "+0%",
        "వేగంగా": "+10%",
    }
    try:
        result = synthesize_telugu_speech(
            text=dialogue,
            voice=voice_label,
            output_file=str(output_file),
            rate=rates.get(rate_label, "+0%"),
            timeout_seconds=90,
        )
    except TeluguTTSSetupError as exc:
        raise gr.Error(str(exc)) from exc
    return str(result)


@spaces.GPU(duration=120)
def generate_new_scene(prompt_te, aspect_ratio, reference_path):
    """Render a short new shot only when an operator has mounted the weights."""
    wan_repo = os.environ.get("WAN_REPO_PATH", "").strip()
    checkpoint = os.environ.get("WAN_TI2V_CHECKPOINT", "").strip()
    if not wan_repo or not checkpoint:
        raise gr.Error(
            "GPU generator ఇంకా configure కాలేదు. Hugging Face Spaceలో "
            "WAN_REPO_PATH మరియు WAN_TI2V_CHECKPOINT సిద్ధం చేసిన తర్వాత మాత్రమే "
            "ఈ బటన్ పనిచేస్తుంది. మోడల్ weights ఆటోమేటిక్‌గా download కావు."
        )
    if not (prompt_te or "").strip():
        raise gr.Error("కొత్త సన్నివేశం కోసం కథను తెలుగులో రాయండి.")
    if reference_path:
        _file_info(reference_path, "క్యారెక్టర్ రిఫరెన్స్")
    output_dir = Path(tempfile.mkdtemp(prefix="macherla_ti2v_"))
    output_file = output_dir / "generated_scene.mp4"
    try:
        rendered = run_ti2v_job(
            wan_repo=wan_repo,
            checkpoint_dir=checkpoint,
            prompt=prompt_te,
            output_file=str(output_file),
            aspect_ratio=aspect_ratio,
            frame_num=41,
            reference_image=reference_path or None,
            timeout_seconds=110,
        )
    except TI2VSetupError as exc:
        raise gr.Error(str(exc)) from exc
    return str(rendered)


@spaces.GPU(duration=120)
def animate_or_replace_character(video_path, reference_path, mode, resolution):
    """Animate/replace a reference character in the uploaded driving video."""
    wan_repo = os.environ.get("WAN_REPO_PATH", "").strip()
    checkpoint = os.environ.get("WAN_ANIMATE_CHECKPOINT", "").strip()
    if not wan_repo or not checkpoint:
        raise gr.Error(
            "Wan2.2 Animate ఇంకా configure కాలేదు. Spaceలో WAN_REPO_PATH మరియు "
            "WAN_ANIMATE_CHECKPOINT సిద్ధం చేసిన తర్వాత మాత్రమే ఇది పనిచేస్తుంది. "
            "మోడల్ weights ఆటోమేటిక్‌గా download కావు."
        )
    _file_info(video_path, "మూల వీడియో")
    _file_info(reference_path, "క్యారెక్టర్ ఫోటో")
    if mode not in {"animate_reference", "replace_character"}:
        raise gr.Error("ఈ tabలో animate_reference లేదా replace_character మాత్రమే ఎంచుకోండి.")
    width, height = (720, 1280) if resolution == "9:16" else (1280, 720)
    output_dir = Path(tempfile.mkdtemp(prefix="macherla_animate_"))
    try:
        rendered = run_wan_animate_job(
            wan_repo=wan_repo,
            checkpoint_dir=checkpoint,
            video_path=video_path,
            reference_image=reference_path,
            output_dir=str(output_dir),
            mode=mode,
            resolution_width=width,
            resolution_height=height,
            timeout_seconds=110,
        )
    except WanSetupError as exc:
        raise gr.Error(str(exc)) from exc
    return str(rendered)


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
        "# 🎬 Macherla Guru — AI Video Worker\n"
        "తెలుగు కథ ఆధారంగా కొత్త సన్నివేశం తయారు చేయడానికి ప్రయోగాత్మక వర్కర్. "
        "మోడల్ ఫైల్స్ సిద్ధంగా ఉన్నప్పుడు మాత్రమే నిజమైన MP4 render ప్రారంభమవుతుంది."
    )
    with gr.Tab("తెలుగు వాయిస్"):
        dialogue = gr.Textbox(
            label="తెలుగు డైలాగ్",
            lines=4,
            placeholder="ఉదా: గిన్నెలు నీట్‌గా తోమలేదని చీపురుతో కొట్టిందిరా!",
        )
        voice = gr.Radio(
            choices=list(TELUGU_VOICES.keys()),
            value="Mohan (పురుష వాయిస్)",
            label="వాయిస్",
        )
        speed = gr.Radio(
            choices=["నెమ్మదిగా", "సాధారణం", "వేగంగా"],
            value="సాధారణం",
            label="మాట్లాడే వేగం",
        )
        voice_button = gr.Button("తెలుగు వాయిస్ తయారు చేయి", variant="primary")
        voice_output = gr.Audio(label="తయారైన తెలుగు MP3", type="filepath")
        voice_button.click(create_telugu_voice, [dialogue, voice, speed], voice_output)
        gr.Markdown(
            "గమనిక: ఇది ఆన్‌లైన్ TTS సేవ. MP3 మాత్రమే తయారవుతుంది; "
            "వీడియోలో పెదవుల కదలికలకు సరిపోల్చడం ఇంకా కలపలేదు."
        )
    with gr.Tab("పాత్రల డైలాగ్ ఆడియో"):
        gr.Markdown(
            "ప్రతి లైన్‌ను **పాత్ర పేరు|వాయిస్|తెలుగు డైలాగ్** రూపంలో రాయండి. "
            "ఉదాహరణకు PJ Babu, యముడు ఇద్దరికీ వేర్వేరు లైన్లు ఇవ్వవచ్చు."
        )
        dialogue_script = gr.Textbox(
            label="పాత్రల డైలాగ్ స్క్రిప్ట్",
            lines=7,
            value=(
                "PJ Babu|Mohan (పురుష వాయిస్)|ఏమైంది స్వామీ?\\n"
                "యముడు|Mohan (పురుష వాయిస్)|గిన్నెలు నీట్‌గా తోమలేదని చీపురుతో కొట్టిందిరా!"
            ),
        )
        dialogue_gap = gr.Radio(
            choices=["వెంటనే", "చిన్న విరామం", "కొంచెం ఎక్కువ"],
            value="చిన్న విరామం",
            label="డైలాగ్‌ల మధ్య విరామం",
        )
        dialogue_rate = gr.Radio(
            choices=["నెమ్మదిగా", "సాధారణం", "వేగంగా"],
            value="సాధారణం",
            label="మాట్లాడే వేగం",
        )
        dialogue_button = gr.Button("పాత్రల డైలాగ్ ఆడియో తయారు చేయి", variant="primary")
        dialogue_output = gr.Audio(label="కలిపిన తెలుగు డైలాగ్ WAV", type="filepath")
        dialogue_button.click(
            create_dialogue_soundtrack,
            inputs=[dialogue_script, dialogue_gap, dialogue_rate],
            outputs=dialogue_output,
        )
        gr.Markdown(
            "గమనిక: ఇది పాత్రల డైలాగ్‌లను క్రమంగా కలిపిన ఆడియో ట్రాక్ మాత్రమే. "
            "ఇంకా క్యారెక్టర్ పెదవుల కదలికలకు sync చేయదు; వీడియోలో ఆటోమేటిక్‌గా కలపదు."
        )
    with gr.Tab("కొత్త సన్నివేశం"):
        prompt = gr.Textbox(
            label="సన్నివేశం / డైలాగ్ సూచన (తెలుగులో)",
            lines=5,
            placeholder="ఉదా: యముడు దున్నపోతుపై భయపడుతూ వస్తాడు...",
        )
        ratio = gr.Radio(choices=["9:16", "16:9"], value="9:16", label="Aspect ratio")
        ref_image = gr.Image(label="ఐచ్చిక క్యారెక్టర్ రిఫరెన్స్ ఫోటో", type="filepath")
        render_button = gr.Button("కొత్త సన్నివేశం తయారు చేయి", variant="primary")
        rendered_video = gr.Video(label="తయారైన సన్నివేశం (MP4)")
        render_button.click(
            generate_new_scene,
            inputs=[prompt, ratio, ref_image],
            outputs=rendered_video,
        )
    with gr.Tab("క్యారెక్టర్ మార్చు / animate"):
        source_video = gr.Video(label="మూల వీడియో (డ్రైవింగ్ వీడియో)", sources=["upload"])
        character_image = gr.Image(label="కొత్త క్యారెక్టర్ రిఫరెన్స్ ఫోటో", type="filepath")
        character_mode = gr.Radio(
            choices=[
                ("ఫోటో క్యారెక్టర్‌కు వీడియో కదలికలు ఇవ్వు", "animate_reference"),
                ("వీడియోలోని క్యారెక్టర్‌ను మార్చు", "replace_character"),
            ],
            value="animate_reference",
            label="పని రకం",
        )
        character_ratio = gr.Radio(choices=["9:16", "16:9"], value="9:16", label="Resolution ratio")
        animate_button = gr.Button("క్యారెక్టర్ వీడియో తయారు చేయి", variant="primary")
        character_output = gr.Video(label="తయారైన క్యారెక్టర్ వీడియో (MP4)")
        animate_button.click(
            animate_or_replace_character,
            inputs=[source_video, character_image, character_mode, character_ratio],
            outputs=character_output,
        )
    with gr.Tab("మూల వీడియో తనిఖీ"):
        with gr.Row():
            video = gr.Video(label="మూల వీడియో", sources=["upload"])
            reference = gr.Image(label="క్యారెక్టర్ రిఫరెన్స్", type="filepath")
        story = gr.Textbox(label="కథ / సూచన (తెలుగులో)", lines=5)
        mode = gr.Radio(
            choices=["animate_reference", "replace_character", "story_driven_new_scenes"],
            value="animate_reference",
            label="పని రకం",
        )
        source_ratio = gr.Radio(choices=["9:16", "16:9", "1:1"], value="9:16", label="Aspect ratio")
        prepare = gr.Button("ఇన్‌పుట్‌లను తనిఖీ చేయి", variant="primary")
        manifest = gr.Code(label="Job manifest", language="json")
        status = gr.Textbox(label="స్థితి")
        prepare.click(prepare_job, [video, reference, story, mode, source_ratio], [manifest, status])
    with gr.Tab("GPU స్థితి"):
        gpu_button = gr.Button("GPU ఉందో తనిఖీ చేయి")
        gpu_result = gr.Textbox(label="GPU సమాచారం", lines=4)
        gpu_button.click(inspect_gpu, outputs=gpu_result)

    gr.Markdown(
        "### పరిమితులు\n"
        "- కొత్త సన్నివేశాల కోసం Wan2.2 TI2V-5B runner కనెక్ట్ చేయబడింది; "
        "కానీ model weights / GPU ఇంకా configure చేయలేదు.\n"
        "- పాత వీడియోలో క్యారెక్టర్ animation/replacement tab ఉంది; కానీ WAN_ANIMATE_CHECKPOINT, GPU లేకుండా render జరగదు.\n"
        "- తెలుగు పాత్రల డైలాగ్‌లను వేర్వేరుగా synthesize చేసి, విరామాలతో ఒక WAV soundtrackగా కలపవచ్చు; lip-sync, video muxing, multi-scene stitching, sound effects ఇంకా చేయాల్సి ఉంది.\n"
        "- మోడల్ weights ఆటోమేటిక్‌గా download కావు; paid hardware అనుమతి లేకుండా enable చేయరాదు."
    )


if __name__ == "__main__":
    demo.queue(max_size=4).launch()
