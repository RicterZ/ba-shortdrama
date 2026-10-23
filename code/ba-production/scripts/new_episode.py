#!/usr/bin/env python3
"""Create a structured, empty episode directory.

Example:
    uv run python scripts/new_episode.py 003-summer-patch \
        --title "夏日补丁" --characters saiba-momoi --kicker "GAME DEVELOPMENT DEPARTMENT"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

TEMPLATES = {"blue-archive"}

SUBDIRS = [
    "audio",
    "manifests",
    "preview",
    "project",
    "output",
    "logs",
    "raws/images",
    "raws/audio",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="新建一集短剧的目录与骨架文件")
    parser.add_argument("episode_id", help="剧集目录名，例如 003-summer-patch")
    parser.add_argument("--title", default="未命名短剧")
    parser.add_argument("--characters", default="saiba-momoi", help="逗号分隔的角色 id")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--template", default="blue-archive", help="视频模板 id")
    parser.add_argument("--accent", default="#e78caf")
    parser.add_argument("--kicker", default="")
    parser.add_argument("--intro-title", default="")
    parser.add_argument("--intro-subtitle", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.template not in TEMPLATES:
        raise SystemExit(f"未知模板 {args.template!r}，可选：{', '.join(sorted(TEMPLATES))}")
    episode = lib.VIDEOS / args.episode_id
    if episode.exists():
        raise SystemExit(f"剧集目录已存在：{episode}")

    characters = [item.strip() for item in args.characters.split(",") if item.strip()]
    for cid in characters:
        try:
            lib.read_character(cid)
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc

    for subdir in SUBDIRS:
        (episode / subdir).mkdir(parents=True, exist_ok=True)

    config = {
        "id": args.episode_id,
        "title": args.title,
        "characters": characters,
        "width": args.width,
        "height": args.height,
        "fps": args.fps,
        "template": args.template,
        "status": "draft",
        "paid_api_budget": 0,
        "publication_approved": False,
        "style": {
            "accent": args.accent,
            "font_family": "PingFang SC",
        },
        "subtitle": lib.DEFAULT_SUBTITLE,
        "timing": lib.DEFAULT_TIMING,
    }
    if args.intro_title or args.kicker or args.intro_subtitle:
        config["intro"] = {
            "durationInFrames": lib.DEFAULT_TIMING["intro_frames"],
            "kicker": args.kicker,
            "title": args.intro_title or args.title,
            "subtitle": args.intro_subtitle,
        }

    lib.write_json(episode / "episode.yaml", config)
    lib.write_json(episode / "script.json", [])
    lib.write_json(episode / "storyboard.json", {"shots": []})
    lib.write_json(
        episode / "review.json",
        {
            "status": "draft",
            "schema_and_hash_validation": "not_run",
            "full_audio_listened": False,
            "preview_frame_reviewed": False,
            "publication_approved": False,
            "missing": ["script", "storyboard"],
        },
    )

    print(f"已创建：{episode}")
    print("下一步：")
    print(f"  1. 编辑 {episode / 'script.json'}：每句台词包含 speaker / emotion / text")
    print(f"  2. 编辑 {episode / 'storyboard.json'}：镜头引用台词 id")
    print(f"  3. uv run python scripts/prepare.py --episode {args.episode_id}")
    print(f"  4. uv run python scripts/validate.py --episode {args.episode_id}")
    print(f"  5. uv run python scripts/render.py --episode {args.episode_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
