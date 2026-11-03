"""Build and run Wan2.2-Animate CLI jobs in an isolated GPU worker.

No weights are downloaded automatically. The runner uses argument arrays (never
shell=True), bounded timeouts, and verifies that an MP4 was actually produced.
"""
from __future__ import annotations

import subprocess
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
    offload_model: bool = True,
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
    if not (checkpoint / "process_checkpoint").is_dir():
        raise WanSetupError("Wan2.2 process_checkpoint directory is missing.")
    if not video.is_file() or video.stat().st_size == 0:
        raise WanSetupError("Source video is missing or empty.")
    if not reference.is_file() or reference.stat().st_size == 0:
        raise WanSetupError("Character reference image is missing or empty.")

    output.mkdir(parents=True, exist_ok=True)
    processed = output / "process_results"
    preprocess = [
        "python", str(preprocess_script),
        "--ckpt_path", str(checkpoint / "process_checkpoint"),
        "--video_path", str(video),
        "--refer_path", str(reference),
        "--save_path", str(processed),
        "--resolution_area", str(resolution_width), str(resolution_height),
    ]
    generate = [
        "python", str(repo / "generate.py"),
        "--task", "animate-14B",
        "--ckpt_dir", str(checkpoint),
        "--src_root_path", str(processed),
        "--refert_num", "1",
        "--save_file", str(output / "wan_animate_output.mp4"),
    ]
    if offload_model:
        generate.extend(["--offload_model", "True"])

    if mode == "animate_reference":
        preprocess.extend(["--retarget_flag", "--use_flux"])
    else:
        preprocess.extend([
            "--iterations", "3", "--k", "7", "--w_len", "1", "--h_len", "1",
            "--replace_flag",
        ])
        generate.extend(["--replace_flag", "--use_relighting_lora"])

    return preprocess, generate


def run_wan_animate_job(
    *,
    wan_repo: str,
    checkpoint_dir: str,
    video_path: str,
    reference_image: str,
    output_dir: str,
    mode: str = "animate_reference",
    timeout_seconds: int = 2700,
    offload_model: bool = True,
) -> Path:
    """Run preprocessing and inference; return only a verified non-empty MP4."""
    if timeout_seconds < 60:
        raise WanSetupError("Inference timeout must be at least 60 seconds.")
    preprocess, generate = build_wan_animate_commands(
        wan_repo=wan_repo,
        checkpoint_dir=checkpoint_dir,
        video_path=video_path,
        reference_image=reference_image,
        output_dir=output_dir,
        mode=mode,
        offload_model=offload_model,
    )
    repo = Path(wan_repo).expanduser().resolve()
    output_file = Path(output_dir).expanduser().resolve() / "wan_animate_output.mp4"
    for label, command in (("preprocessing", preprocess), ("inference", generate)):
        try:
            result = subprocess.run(
                command,
                cwd=str(repo),
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise WanSetupError(f"Wan2.2 {label} timed out.") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise WanSetupError(f"Wan2.2 {label} failed: {detail[-2000:]}") from exc
    if not output_file.is_file() or output_file.stat().st_size < 12:
        raise WanSetupError("Wan2.2 finished without producing a non-empty MP4.")
    with output_file.open("rb") as stream:
        header = stream.read(12)
    if header[4:8] != b"ftyp":
        raise WanSetupError("Output file does not have a valid MP4 container header.")
    return output_file
