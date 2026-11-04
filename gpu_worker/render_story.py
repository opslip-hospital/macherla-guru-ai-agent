"""Command-line entry point for full story rendering on a configured GPU host.

Example:
  WAN_REPO_PATH=/opt/Wan2.2 WAN_TI2V_CHECKPOINT=/models/Wan2.2-TI2V-5B \
    python render_story.py --manifest render_manifest.json --reference pj-babu.png --output-dir ./rendered

This script does not download model weights or create cloud resources.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from .story_render_runner import (
        StoryRenderPipelineError,
        load_manifest_file,
        render_story_to_mp4,
    )
except ImportError:
    from story_render_runner import (
        StoryRenderPipelineError,
        load_manifest_file,
        render_story_to_mp4,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a Telugu multi-scene story using Wan2.2 TI2V-5B.")
    parser.add_argument("--manifest", required=True, help="Validated scene render manifest JSON")
    parser.add_argument("--reference", default=None, help="Optional common character reference image")
    parser.add_argument("--output-dir", default="./macherla_story_output", help="Directory for scene clips and final MP4")
    parser.add_argument("--wan-repo", default=os.environ.get("WAN_REPO_PATH"), help="Wan2.2 repository path (or WAN_REPO_PATH)")
    parser.add_argument("--checkpoint", default=os.environ.get("WAN_TI2V_CHECKPOINT"), help="TI2V-5B checkpoint directory (or WAN_TI2V_CHECKPOINT)")
    parser.add_argument("--timeout", type=int, default=2700, help="Timeout in seconds per generated scene")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.wan_repo or not args.checkpoint:
        print(
            "తప్పనిసరి: WAN_REPO_PATH మరియు WAN_TI2V_CHECKPOINT environment variables ఇవ్వాలి.",
            file=sys.stderr,
        )
        return 2
    try:
        manifest = load_manifest_file(args.manifest)
        result = render_story_to_mp4(
            manifest,
            wan_repo=args.wan_repo,
            checkpoint_dir=args.checkpoint,
            output_dir=args.output_dir,
            reference_image=args.reference,
            render_timeout_seconds=args.timeout,
        )
    except (StoryRenderPipelineError, ValueError, OSError) as exc:
        print(f"Render failed: {exc}", file=sys.stderr)
        return 1
    print(f"Final MP4: {Path(result).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
