"""Build safe, reproducible Wan2.2-Animate CLI commands.

This adapter does not download weights or execute GPU inference. It validates a
local checkout and returns argument lists for the official preprocess/generate
scripts, so a future GPU worker can invoke them without shell interpolation.
"""
from __future__ import annotations

from pathlib import Path


class WanSetupError(RuntimeError):
    pass


def build_wan_animate_commands(
    *,
    wan_repo: str,
    checkpoint_dir: str,
    video_path: str,
    reference_image: str,
    output_dir: str,
    mode: str = "animate_reference",
    resolution_width: int = 1280,
    resolution_height: int = 720,
) -> tuple[list[str], list[str]]:
    repo = Path(wan_repo).expanduser().resolve()
    checkpoint = Path(checkpoint_dir).expanduser().resolve()
    video = Path(video_path).expanduser().resolve()
    reference = Path(reference_image).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()

    if mode not in {"animate_reference", "replace_character"}:
        raise WanSetupError(
            "Wan2.2-Animate supports animate_reference or replace_character; "
            "story_driven_new_scenes needs a separate video-generation model."
        )
    if resolution_width < 256 or resolution_height < 256:
        raise WanSetupError("Resolution must be at least 256x256.")
    if not (repo / "generate.py").is_file():
        raise WanSetupError("Wan2.2 repository is missing generate.py.")
    preprocess_script = repo / "wan/modules/animate/preprocess/preprocess_data.py"
    if not preprocess_script.is_file():
        raise WanSetupError("Wan2.2 preprocessing script was not found.")
    if not checkpoint.is_dir():
        raise WanSetupError("Wan2.2-Animate-14B checkpoint directory is missing.")
    if not video.is_file() or video.stat().st_size == 0:
        raise WanSetupError("Source video is missing or empty.")
    if not reference.is_file() or reference.stat().st_size == 0:
        raise WanSetupError("Character reference image is missing or empty.")

    output.mkdir(parents=True, exist_ok=True)
    processed = output / "process_results"
    preprocess = [
        "python",
        str(preprocess_script),
        "--ckpt_path", str(checkpoint / "process_checkpoint"),
        "--video_path", str(video),
        "--refer_path", str(reference),
        "--save_path", str(processed),
        "--resolution_area", str(resolution_width), str(resolution_height),
    ]
    generate = [
        "python",
        str(repo / "generate.py"),
        "--task", "animate-14B",
        "--ckpt_dir", str(checkpoint),
        "--src_root_path", str(processed),
        "--refert_num", "1",
        "--save_file", str(output / "wan_animate_output.mp4"),
    ]

    if mode == "animate_reference":
        preprocess.extend(["--retarget_flag", "--use_flux"])
    else:
        preprocess.extend([
            "--iterations", "3", "--k", "7", "--w_len", "1", "--h_len", "1",
            "--replace_flag",
        ])
        generate.extend(["--replace_flag", "--use_relighting_lora"])

    return preprocess, generate
