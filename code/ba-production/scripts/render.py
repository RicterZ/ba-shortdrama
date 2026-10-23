#!/usr/bin/env python3
"""Render an episode with Remotion using its generated scene.json props.

Examples:
    uv run python scripts/render.py --episode 002-hidden-ending --profile preview
    uv run python scripts/render.py --episode 002-hidden-ending --mode still --frame 120
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

BA_PRODUCTION = Path(__file__).resolve().parents[1]
REMOTION = BA_PRODUCTION / "node_modules" / ".bin" / "remotion"
COMPOSITION = "BAEpisode"
TEMPLATES = {"blue-archive": BA_PRODUCTION / "templates" / "index.tsx"}
DEFAULT_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


PROFILES = {
    # Review renders fewer, smaller frames without changing source timing.
    "preview": {
        "suffix": "-preview",
        "scale": "0.5",
        "frame_step": 3,
        "crf": "28",
        "preset": "ultrafast",
        "concurrency": 4,
        "image": ["--image-format=jpeg", "--jpeg-quality=70"],
    },
    # Delivery cut: 2x output scale, high-quality encode. Review first, then render final.
    "final": {"suffix": "", "scale": "2", "crf": "14", "preset": "slow", "concurrency": 4, "image": []},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="渲染一集成片或预览帧")
    parser.add_argument("--episode", required=True)
    parser.add_argument("--mode", choices=["video", "still", "both"], default="video")
    parser.add_argument("--frame", action="append", type=int, default=[], help="预览帧，可重复")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default=None,
        help="preview：快速低码率审片；final：高分辨率成片。渲染视频时必填",
    )
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--out", default="", help="成片文件名，默认 <episode-id>[-preview].mp4")
    args = parser.parse_args()
    if args.mode in ("video", "both") and args.profile is None:
        parser.error("渲染视频需要 --profile preview 或 --profile final（用 npm run ep:preview / ep:final）")
    return args


def chrome_flags() -> list[str]:
    flags = []
    if os.environ.get("REMOTION_GL"):
        flags.append(f"--gl={os.environ['REMOTION_GL']}")
    candidate = os.environ.get("CHROME_PATH")
    path = Path(candidate) if candidate else DEFAULT_CHROME
    if path.is_file():
        flags.append(f"--browser-executable={path}")
    return flags


def run(command: list[str]) -> None:
    print(">", " ".join(str(part) for part in command))
    started = time.monotonic()
    try:
        subprocess.run([str(part) for part in command], cwd=BA_PRODUCTION, check=True)
    finally:
        print(f"Render elapsed: {time.monotonic() - started:.2f}s", flush=True)


def main() -> int:
    args = parse_args()
    episode = lib.resolve_episode(args.episode, lock=True)
    scene_path = episode / "project" / "scene.json"
    if not scene_path.is_file():
        raise SystemExit(f"缺少 {scene_path}，先运行 prepare.py")
    scene = lib.load_json(scene_path)
    template_id = scene.get("episode", {}).get("template", "blue-archive")
    entry = TEMPLATES.get(template_id)
    if entry is None:
        raise SystemExit(f"未知模板 {template_id!r}，可选：{', '.join(TEMPLATES)}")
    fps = int(scene["episode"]["fps"])
    duration = int(scene["episode"]["durationInFrames"])

    if not REMOTION.is_file():
        raise SystemExit(f"找不到 Remotion：{REMOTION}，先在 code/ba-production 运行 npm install")

    if args.mode in ("video", "both"):
        profile = PROFILES[args.profile]
        suffix = profile["suffix"]
        encode_flags = [
            f"--scale={profile['scale']}",
            f"--crf={profile['crf']}",
            f"--x264-preset={profile['preset']}",
            f"--every-nth-frame={profile.get('frame_step', 1)}",
            *profile.get("image", []),
        ]
        output = episode / "output" / (args.out or f"{episode.name}{suffix}.mp4")
        output.parent.mkdir(parents=True, exist_ok=True)
        concurrency = args.concurrency if args.concurrency is not None else profile["concurrency"]
        run(
            [
                REMOTION,
                "render",
                entry,
                COMPOSITION,
                output,
                "--props",
                scene_path,
                "--public-dir",
                episode / "raws",
                f"--concurrency={concurrency}",
                *encode_flags,
                *chrome_flags(),
            ]
        )
        media = lib.probe_media(output)
        kinds = {stream.get("codec_type") for stream in media.get("streams", [])}
        print(f"成片：{output}  {float(media['format']['duration']):.2f}s  流：{sorted(kinds)}")

    if args.mode in ("still", "both"):
        frames = args.frame
        if not frames:
            lines = [line for shot in scene.get("shots", []) for line in shot.get("lines", [])]
            frames = [(lines[0]["from"] + 12) if lines else duration // 2]
        preview = episode / "preview"
        preview.mkdir(parents=True, exist_ok=True)
        for frame in frames:
            if not 0 <= frame < duration:
                raise SystemExit(f"预览帧 {frame} 超出范围 0-{duration - 1}")
            output = preview / f"frame-{frame:04d}.png"
            run(
                [
                    REMOTION,
                    "still",
                    entry,
                    COMPOSITION,
                    output,
                    "--frame",
                    str(frame),
                    "--props",
                    scene_path,
                    "--public-dir",
                    episode / "raws",
                    "--image-format",
                    "png",
                    *chrome_flags(),
                ]
            )
            print(f"预览帧：{output}")

    print(f"完成：{episode.name} @ {fps}fps, {duration} 帧")
    return 0


if __name__ == "__main__":
    sys.exit(main())
