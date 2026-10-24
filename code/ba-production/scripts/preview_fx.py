#!/usr/bin/env python3
"""Preview one bubble or one character action without an episode.

The clip is a single character on a flat background. Bubble placement, scale,
and duration stay on the preset; this command does not accept x/y/scale/duration.

Examples:
    npm run fx -- preview Heart --character saiba-momoi
    npm run fx -- preview hophop --character saiba-momoi --still
"""
from __future__ import annotations

import argparse
import math
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
import prepare  # noqa: E402
import render  # noqa: E402
from sprite_coordinates import read_coordinates  # noqa: E402

FPS = 30
WIDTH = 1280
HEIGHT = 720

# Length of the performance itself. closeup and hide hold, so the preview
# shows one second of the held pose instead of a zero-length clip.
ACTION_SECONDS = {
    "jump": 0.25,
    "hophop": 0.5,
    "greeting": 0.4,
    "shake": 0.24,
    "stiff": 0.4,
    "closeup": 1.0,
    "falldownL": 1.87,
    "falldownR": 1.87,
    "hide": 1.0,
}


def classify(name: str) -> str:
    bubble = name in prepare.BUBBLE_PRESETS
    action = name in ACTION_SECONDS
    if bubble and action:
        raise SystemExit(f"{name} 同时是气泡和动作，无法预览")
    if bubble:
        return "bubble"
    if action:
        return "action"
    bubbles = ", ".join(sorted(prepare.BUBBLE_PRESETS))
    actions = ", ".join(ACTION_SECONDS)
    raise SystemExit(f"未知预览 {name!r}。气泡：{bubbles}。动作：{actions}")


def cue_seconds(kind: str, name: str) -> float:
    if kind == "bubble":
        return float(prepare.BUBBLE_PRESETS[name]["seconds"])
    return ACTION_SECONDS[name]


def frames_for(seconds: float, fps: int = FPS) -> int:
    """Frames that still show the cue. The end boundary itself is already gone."""
    return max(1, math.ceil(seconds * fps - 1e-9))


def choose_frame(duration: int, requested: int | None) -> int:
    frame = duration // 2 if requested is None else requested
    if isinstance(frame, bool) or not isinstance(frame, int) or not 0 <= frame < duration:
        raise SystemExit(f"预览帧 {frame} 超出范围 0-{duration - 1}")
    return frame


def build_preview(
    character_id: str,
    name: str,
    raws: Path,
    *,
    outfit_id: str | None = None,
    emotion: str = "default",
    mute: bool = False,
) -> dict:
    kind = classify(name)
    char = lib.read_character(character_id)
    outfit_id = outfit_id or char["default_outfit"]
    if outfit_id not in char["outfits"]:
        raise SystemExit(f"{character_id} 没有服装 {outfit_id}")
    if raws.exists():
        shutil.rmtree(raws)
    raws.mkdir(parents=True)
    warnings: list[str] = []
    fallbacks: set[str] = set()
    default_sprite = prepare.copy_sprite(char, outfit_id, "default", raws, warnings, fallbacks)
    emotion_sprite = default_sprite
    if emotion != "default":
        emotion_sprite = prepare.copy_sprite(char, outfit_id, emotion, raws, warnings, fallbacks)
    sprites = {"default": default_sprite}
    if emotion != "default":
        sprites[emotion] = emotion_sprite

    seconds = cue_seconds(kind, name)
    duration = frames_for(seconds)
    actions: list[dict] = []
    bubbles: list[dict] = []
    spine_bounds = None
    if kind == "bubble":
        skeleton = (char["profile"].get("outfits") or {}).get(outfit_id, {}).get("spine")
        if not isinstance(skeleton, str) or not skeleton:
            raise SystemExit(
                f"{character_id}/{outfit_id}: bubbles require a matching outfit.spine export; refusing guessed coordinates"
            )
        sprite_path = char["outfits"][outfit_id]["sprites"]["default"]["path"]
        spine_bounds = read_coordinates(char["dir"] / skeleton, sprite_path)
        cue = {"name": name, "startFrame": 0, "sound": not mute}
        prepare.snapshot_bubbles([{"characters": [{"bubbles": [cue]}]}], raws)
        bubbles.append(cue)
    else:
        actions.append({"name": name, "startFrame": 0})

    return {
        "schema_version": 2,
        "episode": {
            "id": f"fx-{character_id}-{name}",
            "title": name,
            "template": "blue-archive",
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "durationInFrames": duration,
            "style": {
                "accent": char["profile"].get("color", "#e78caf"),
                "font_family": "PingFang SC",
            },
        },
        "characters": {
            character_id: {
                "name": char["profile"].get("name", character_id),
                "color": char["profile"].get("color", "#c44b82"),
                "club": (char["profile"].get("persona") or {}).get("club", ""),
                "school": (char["profile"].get("persona") or {}).get("school", ""),
                "default_outfit": outfit_id,
                "outfits": {
                    outfit_id: {
                        "name": char["outfits"][outfit_id]["name"],
                        "sprites": sprites,
                        "spineBounds": spine_bounds,
                    }
                },
            }
        },
        "shots": [
            {
                "id": "preview",
                "from": 0,
                "durationInFrames": duration,
                "camera": "static",
                "background": {"type": "gradient", "value": "linear-gradient(125deg,#e4f7f5,#fbe6ed)"},
                "lines": [],
                "characters": [
                    {
                        "id": character_id,
                        "outfit": outfit_id,
                        "x": 0.5,
                        "bottom": lib.DEFAULT_CHARACTER_BOTTOM,
                        "height": lib.DEFAULT_CHARACTER_HEIGHT,
                        "scale": 1.0,
                        "entrance": "none",
                        "exit": "none",
                        "emotion": emotion,
                        "actions": actions,
                        "bubbles": bubbles,
                        "facing": "right",
                    }
                ],
            }
        ],
    }


def render_preview(scene: dict, raws: Path, output: Path, *, still: bool, frame: int | None) -> None:
    scene_path = raws.parent / "scene.json"
    lib.write_json(scene_path, scene)
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = int(scene["episode"]["durationInFrames"])
    remotion = render.remotion_invocation()
    entry = render.TEMPLATES["blue-archive"]
    shared = [
        "--props",
        scene_path,
        "--public-dir",
        raws,
        *render.chrome_flags(),
    ]
    if still:
        chosen = choose_frame(duration, frame)
        render.run([
            *remotion,
            "still",
            entry,
            render.COMPOSITION,
            output,
            "--frame",
            str(chosen),
            "--image-format",
            "png",
            *shared,
        ])
        return
    # Half scale like the episode preview profile, but keep every frame.
    # every-nth-frame=3 would collapse a half-second hop into a couple of frames.
    render.run([
        *remotion,
        "render",
        entry,
        render.COMPOSITION,
        output,
        "--scale=0.5",
        "--crf=28",
        "--x264-preset=ultrafast",
        "--every-nth-frame=1",
        "--concurrency=4",
        *shared,
    ])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="预览一个气泡或一个角色动作")
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview", help="渲染一个气泡或一个动作")
    preview.add_argument("name", help="气泡预设名或动作名，例如 Heart、hophop")
    preview.add_argument("--character", required=True)
    preview.add_argument("--outfit", default="", help="默认用 profile 的 default_outfit")
    preview.add_argument("--emotion", default="default")
    preview.add_argument("--still", action="store_true", help="只出中间一帧 PNG")
    preview.add_argument("--frame", type=int, default=None, help="配合 --still 指定帧")
    preview.add_argument("--mute", action="store_true", help="气泡不播放音效")
    preview.add_argument("--out", default="", help="输出文件，默认 local/work/fx-preview/")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    work = lib.ROOT / "local" / "work" / "fx-preview" / f"{args.character}-{args.name}"
    raws = work / "raws"
    scene = build_preview(
        args.character,
        args.name,
        raws,
        outfit_id=args.outfit or None,
        emotion=args.emotion,
        mute=args.mute,
    )
    suffix = "png" if args.still else "mp4"
    output = Path(args.out) if args.out else work.parent / f"{args.character}-{args.name}.{suffix}"
    if not output.is_absolute():
        output = lib.ROOT / output
    render_preview(scene, raws, output, still=args.still, frame=args.frame)
    print(f"预览：{output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
