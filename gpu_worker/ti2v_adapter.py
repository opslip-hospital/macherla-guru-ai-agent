"""Wan2.2 TI2V-5B adapter for prompt-driven new scene generation.

Supports text-to-video and image-to-video CLI invocation. It does not download
weights; execution is opt-in and validates the resulting MP4.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class TI2VSetupError(RuntimeError):
    pass


def build_ti2v_command(
    *,
    wan_repo: str,
    checkpoint_dir: str,
    prompt: str,
    output_file: str,
    aspect_ratio: str = "9:16",
    frame_num: int = 41,
    reference_image: str | None = None,
) -> list[str]:
    repo = Path(wan_repo).expanduser().resolve()
    checkpoint = Path(checkpoint_dir).expanduser().resolve()
    output = Path(output_file).expanduser().resolve()
    if not prompt or not prompt.strip():
        raise TI2VSetupError("A scene prompt is required.")
    if aspect_ratio not in {"9:16", "16:9"}:
        raise TI2VSetupError("TI2V prototype supports 9:16 or 16:9 output.")
    if frame_num < 5 or (frame_num - 1) % 4 != 0:
        raise TI2VSetupError("frame_num must be 4n+1 and at least 5.")
    if not (repo / "generate.py").is_file():
        raise TI2VSetupError("Wan2.2 repository is missing generate.py.")
    if not checkpoint.is_dir():
        raise TI2VSetupError("Wan2.2-TI2V-5B checkpoint directory is missing.")
    image = None
    if reference_image:
        image = Path(reference_image).expanduser().resolve()
        if not image.is_file() or image.stat().st_size == 0:
            raise TI2VSetupError("Reference image is missing or empty.")

    output.parent.mkdir(parents=True, exist_ok=True)
    size = "704*1280" if aspect_ratio == "9:16" else "1280*704"
    command = [
        "python", str(repo / "generate.py"),
        "--task", "ti2v-5B",
        "--size", size,
        "--frame_num", str(frame_num),
        "--ckpt_dir", str(checkpoint),
        "--offload_model", "True",
        "--convert_model_dtype",
        "--t5_cpu",
        "--prompt", prompt.strip(),
        "--save_file", str(output),
    ]
    if image:
        command.extend(["--image", str(image)])
    return command


def run_ti2v_job(
    *,
    wan_repo: str,
    checkpoint_dir: str,
    prompt: str,
    output_file: str,
    aspect_ratio: str = "9:16",
    frame_num: int = 41,
    reference_image: str | None = None,
    timeout_seconds: int = 2700,
) -> Path:
    if timeout_seconds < 60:
        raise TI2VSetupError("Generation timeout must be at least 60 seconds.")
    command = build_ti2v_command(
        wan_repo=wan_repo,
        checkpoint_dir=checkpoint_dir,
        prompt=prompt,
        output_file=output_file,
        aspect_ratio=aspect_ratio,
        frame_num=frame_num,
        reference_image=reference_image,
    )
    try:
        subprocess.run(
            command,
            cwd=str(Path(wan_repo).expanduser().resolve()),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise TI2VSetupError("Wan2.2 TI2V generation timed out.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise TI2VSetupError(f"Wan2.2 TI2V generation failed: {detail[-2000:]}") from exc

    output = Path(output_file).expanduser().resolve()
    if not output.is_file() or output.stat().st_size < 12:
        raise TI2VSetupError("Wan2.2 TI2V finished without a non-empty MP4.")
    with output.open("rb") as stream:
        header = stream.read(12)
    if header[4:8] != b"ftyp":
        raise TI2VSetupError("Generated file does not have a valid MP4 container header.")
    return output
