#!/usr/bin/env python3
"""Generate voiceover, timing, sprite snapshots and the Remotion scene for one episode.

Voice providers are bound per character profile (API keys live in local/.env).

Example:
    uv run python scripts/prepare.py --episode 002-hidden-ending
    uv run python scripts/prepare.py --episode 001-momoi-pilot --reuse-audio
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
import voice  # noqa: E402

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="准备一集的语音、分镜快照和 Remotion scene")
    parser.add_argument("--episode", required=True, help="剧集 id 或目录路径")
    parser.add_argument("--reuse-audio", action="store_true", help="复用 audio/ 下已有语音，不重新合成")
    parser.add_argument("--voice-timeout", type=int, default=120, help="单句语音超时秒数")
    parser.add_argument(
        "--voice-fallback",
        action="store_true",
        help="主音色失败时使用 profile 里的 fallback（默认直接报错）",
    )
    return parser.parse_args()


# ── sprites ─────────────────────────────────────────────────────────────────


def copy_sprite(
    char: dict,
    outfit_id: str,
    expression: str,
    raws: Path,
    warnings: list[str],
    fallbacks: set[str],
) -> str:
    outfit = char["outfits"][outfit_id]
    sprites = outfit["sprites"]
    resolved = expression if expression in sprites else "default"
    if resolved != expression:
        fallbacks.add(expression)
        key = f"{char['id']}/{outfit_id}:{expression}"
        message = (
            f"{key}：{char['profile'].get('name', char['id'])}（{outfit['name']}）缺少「{expression}」表情，"
            "使用 default 立绘 + 程序化演出"
        )
        if not any(item.startswith(key) for item in warnings):
            warnings.append(message)
    src = sprites[resolved]["path"]
    if not src.is_file():
        raise FileNotFoundError(f"立绘文件不存在：{src}")
    dst = raws / "images" / f"{char['id']}-{outfit_id}-{expression}{src.suffix}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"images/{dst.name}"


# ── timing & shots ──────────────────────────────────────────────────────────


def build_timing(
    script: list[dict],
    characters: dict[str, dict],
    line_outfits: dict[str, str],
    episode: Path,
    fps: int,
    timing_cfg: dict,
    reuse_audio: bool,
    timeout: int,
    allow_fallback: bool,
) -> tuple[list[dict], int, dict]:
    audio_dir = episode / "audio"
    raws_audio = episode / "raws" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    raws_audio.mkdir(parents=True, exist_ok=True)

    cursor = timing_cfg["intro_frames"] + timing_cfg["lead_in_frames"]
    timed: list[dict] = []
    providers: dict[str, int] = {}
    for index, line in enumerate(script):
        char = characters[line["speaker"]]
        outfit_id = line_outfits.get(line["id"], char["default_outfit"])
        target = audio_dir / f"{index:03}.mp3"
        if reuse_audio and target.is_file():
            tts = {"provider": "reused", "voice_id": "", "model": "", "speed": 1.0, "fallback": False}
        else:
            tts = voice.synthesize_line(
                lib.spoken_text(line), char["voice"], target, timeout, allow_fallback
            )
        providers[tts["provider"]] = providers.get(tts["provider"], 0) + 1
        shutil.copy2(target, raws_audio / target.name)

        seconds = lib.probe_duration(target)
        frames = max(
            timing_cfg["min_line_frames"],
            math.ceil(seconds * fps) + timing_cfg["tail_frames"],
        )
        timed.append(
            {
                **line,
                "outfit": outfit_id,
                "start": cursor,
                "frames": frames,
                "seconds": round(seconds, 3),
                "audio": f"audio/{target.name}",
                "tts": tts,
            }
        )
        cursor += frames
    return timed, cursor + timing_cfg["outro_frames"], providers


def shot_scene_key(raw: dict, scene_def: dict | None) -> tuple:
    """What fills the frame, used to decide automatic scene-change cuts."""
    if scene_def is not None:
        return ("scene", scene_def["id"], scene_def["variant"])
    return ("background", json.dumps(raw.get("background"), sort_keys=True, ensure_ascii=False))


def resolve_transition(
    index: int, raw: dict, scene_keys: list[tuple], cfg: dict | None
) -> dict | None:
    """Pick the transition entering shot `index`; None means a hard cut."""
    explicit = raw.get("transition")
    if explicit is not None:
        if index == 0:
            raise SystemExit(f"镜头 {raw['id']} 是第一个镜头，不能声明转场")
        try:
            return lib.parse_transition(explicit, lib.transition_defaults(explicit, cfg))
        except ValueError as exc:
            raise SystemExit(f"镜头 {raw['id']} 的转场无效：{exc}")
    if index == 0 or not cfg:
        return None
    if not isinstance(cfg, dict):
        raise SystemExit("episode.yaml 的 transitions 必须是对象")
    on = cfg.get("on", lib.DEFAULT_TRANSITIONS["on"])
    if on not in ("scene-change", "every-cut", "none"):
        raise SystemExit(f"episode.yaml 的 transitions.on 不支持 {on!r}，可选：scene-change / every-cut / none")
    if on == "none":
        return None
    if on == "scene-change" and scene_keys[index] == scene_keys[index - 1]:
        return None
    try:
        return lib.parse_transition({}, cfg)
    except ValueError as exc:
        raise SystemExit(f"episode.yaml 的 transitions 配置无效：{exc}")


def build_shots(
    board: list[dict],
    timed: list[dict],
    timing_cfg: dict,
    scenes: dict[tuple[str, str | None], dict],
    default_outfits: dict[str, str],
    transitions_cfg: dict | None = None,
) -> tuple[list[dict], int, dict[str, int]]:
    by_id = {line["id"]: line for line in timed}
    flat: list[str] = []
    for shot in board:
        flat.extend(shot.get("lines", []))
    if flat != [line["id"] for line in timed]:
        raise SystemExit(
            "storyboard 的台词覆盖与 script.json 不一致。\n"
            f"storyboard: {flat}\nscript:     {[line['id'] for line in timed]}"
        )

    total = timed[-1]["start"] + timed[-1]["frames"] + timing_cfg["outro_frames"]
    boundaries = [0]
    for index in range(1, len(board)):
        shot = board[index]
        first = by_id[shot["lines"][0]]
        last = by_id[board[index - 1]["lines"][-1]]
        previous_end = last["start"] + last["frames"] + timing_cfg["shot_tail_frames"]
        cut = max(previous_end, first["start"] - timing_cfg["shot_cut_lead_frames"])
        cut = min(cut, first["start"])
        boundaries.append(cut)
    boundaries.append(total)

    # Resolve the scene of every shot up front: an automatic transition depends
    # on whether the frame content actually changes at the cut.
    scene_defs: list[dict | None] = []
    for raw in board:
        scene_def = None
        scene_ref = raw.get("scene")
        if scene_ref:
            scene_id = scene_ref if isinstance(scene_ref, str) else scene_ref["id"]
            variant = None if isinstance(scene_ref, str) else scene_ref.get("variant")
            key = (scene_id, variant)
            if key not in scenes:
                scenes[key] = lib.read_scene(scene_id, variant)
            scene_def = scenes[key]
        scene_defs.append(scene_def)
    scene_keys = [shot_scene_key(raw, scene_def) for raw, scene_def in zip(board, scene_defs)]

    # A transition overlaps the tail of the previous shot with the head of this
    # one, so resolve every cut before laying out the timeline, and reject
    # transitions that are longer than either neighbour.
    transitions = [
        resolve_transition(index, raw, scene_keys, transitions_cfg)
        for index, raw in enumerate(board)
    ]
    for index in range(1, len(board)):
        spec = transitions[index]
        if spec is None:
            continue
        frames = spec["durationInFrames"]
        previous = boundaries[index] - boundaries[index - 1]
        current = boundaries[index + 1] - boundaries[index]
        if frames >= previous or frames >= current:
            raise SystemExit(
                f"镜头 {board[index]['id']} 的转场 {frames} 帧过长："
                f"上一镜头 {previous} 帧、本镜头 {current} 帧，转场必须短于两者"
            )

    # Inserting the transition length as silence at each cut keeps dialogue from
    # overlapping: shot content shifts right by the accumulated padding, while
    # @remotion/transitions overlaps the shots by exactly the same amount, so the
    # final duration only grows by the transitions themselves.
    padding = 0
    starts: list[int] = []
    shifts: list[int] = []
    for index in range(len(board)):
        spec = transitions[index]
        overlap = spec["durationInFrames"] if spec else 0
        padding += overlap
        shifts.append(padding)
        starts.append(boundaries[index] + padding - overlap)

    durations: list[int] = []
    for index in range(len(board)):
        if index + 1 < len(board):
            following = transitions[index + 1]
            durations.append(
                starts[index + 1]
                - starts[index]
                + (following["durationInFrames"] if following else 0)
            )
        else:
            durations.append(boundaries[-1] + padding - starts[index])

    shots: list[dict] = []
    line_shifts: dict[str, int] = {}
    for index, raw in enumerate(board):
        start = starts[index]
        duration = durations[index]
        if duration <= 0:
            raise SystemExit(f"镜头 {raw['id']} 时长为 0，请调整台词或时间参数")
        # Shot-relative authoring fields (choices, buttons, motion, turns) are
        # written from the shot's visible start, so they move by the transition
        # that plays before the shot's own content.
        lead = shifts[index] - (shifts[index - 1] if index else 0)
        content_start = boundaries[index] + shifts[index]
        content_end = boundaries[index + 1] + shifts[index]
        shot_lines = []
        for lid in raw["lines"]:
            line = by_id[lid]
            line_from = line["start"] + shifts[index]
            if not (content_start <= line_from and line_from + line["frames"] <= content_end):
                raise SystemExit(f"镜头 {raw['id']} 与台词 {lid} 的时间范围重叠，请检查时间参数")
            line_shifts[lid] = shifts[index]
            shot_lines.append(
                {
                    "id": line["id"],
                    "speaker": line["speaker"],
                    "outfit": line["outfit"],
                    "emotion": line["emotion"],
                    "text": line["text"],
                    "from": line_from,
                    "durationInFrames": line["frames"],
                    "audio": line["audio"],
                }
            )
        characters = []
        for entry in raw.get("characters", []):
            facing = entry.get("facing", "right")
            if facing not in ("left", "right"):
                raise SystemExit(f"镜头 {raw['id']} 角色 {entry['id']} 的 facing 必须是 left/right")
            turns = []
            for turn in entry.get("turns") or []:
                target = turn.get("to")
                if target not in ("left", "right"):
                    raise SystemExit(f"镜头 {raw['id']} 角色 {entry['id']} 的 turns.to 必须是 left/right")
                if "atLine" in turn:
                    line = next((item for item in shot_lines if item["id"] == turn["atLine"]), None)
                    if line is None:
                        raise SystemExit(
                            f"镜头 {raw['id']} 角色 {entry['id']} 的 turns.atLine={turn['atLine']!r} 不在该镜头台词中"
                        )
                    start_frame = line["from"] - start
                else:
                    start_frame = int(turn.get("startFrame", 0)) + lead
                if not (0 <= start_frame < duration):
                    raise SystemExit(
                        f"镜头 {raw['id']} 角色 {entry['id']} 的转身起点 {start_frame} 超出镜头时长 {duration} 帧"
                    )
                turns.append(
                    {
                        "to": target,
                        "startFrame": start_frame,
                        "durationInFrames": int(turn.get("durationInFrames", 6)),
                    }
                )
            motion = entry.get("motion")
            if motion:
                motion = dict(motion)
                for field in ("startFrame", "endFrame"):
                    if motion.get(field) is not None:
                        motion[field] = int(motion[field]) + lead
            characters.append(
                {
                    "id": entry["id"],
                    "outfit": entry.get("outfit") or default_outfits.get(entry["id"]),
                    "x": entry.get("x", 0.5),
                    "bottom": entry.get("bottom", 0.0),
                    "height": entry.get("height", 0.92),
                    "scale": entry.get("scale", 1.0),
                    "entrance": entry.get("entrance", "fade-in"),
                    "exit": entry.get("exit", "none"),
                    "emotion": entry.get("emotion", "default"),
                    "facing": facing,
                    "turns": turns,
                    "motion": motion,
                }
            )
        background = raw.get("background", "#eef6f4")
        if isinstance(background, str):
            background = {"type": "gradient", "value": background}
        choices = raw.get("choices")
        if choices:
            choices = dict(choices)
            for field in ("fromFrame", "selectFrame", "hideFrame"):
                if choices.get(field) is not None:
                    choices[field] = int(choices[field]) + lead
            for field in ("fromFrame", "selectFrame", "hideFrame"):
                value = choices.get(field)
                if value is not None and not (0 <= int(value) < duration):
                    raise SystemExit(
                        f"镜头 {raw['id']} 的 choices.{field}={value} 超出镜头时长 {duration} 帧"
                    )
            select = choices.get("selectFrame")
            hide = choices.get("hideFrame")
            if select is not None and hide is not None and int(hide) <= int(select):
                raise SystemExit(f"镜头 {raw['id']} 的 choices.hideFrame 必须晚于 selectFrame")
            selected = int(choices.get("selected", 0))
            if not (0 <= selected < len(choices.get("options") or [])):
                raise SystemExit(f"镜头 {raw['id']} 的 choices.selected 超出选项范围")
        buttons = raw.get("buttons") or []
        shifted_buttons = []
        for button in buttons:
            button = dict(button)
            if button.get("pressFrame") is not None:
                button["pressFrame"] = int(button["pressFrame"]) + lead
            press = button.get("pressFrame")
            if press is not None and not (0 <= int(press) < duration):
                raise SystemExit(
                    f"镜头 {raw['id']} 的按钮 {button.get('label')!r} pressFrame={press} 超出镜头时长"
                )
            shifted_buttons.append(button)
        shots.append(
            {
                "id": raw["id"],
                "from": start,
                "durationInFrames": duration,
                "transition": transitions[index],
                "scene": scene_defs[index],
                "background": background,
                "camera": raw.get("camera", "static"),
                "characters": characters,
                "lines": shot_lines,
                "choices": choices,
                "buttons": shifted_buttons,
            }
        )
    return shots, boundaries[-1] + padding, line_shifts


def outfit_for_line(entry: dict, board: list[dict]) -> str:
    """A line uses the outfit declared on its speaker in the owning shot."""
    lid = entry["id"]
    for shot in board:
        if lid not in (shot.get("lines") or []):
            continue
        for char in shot.get("characters") or []:
            if char.get("id") == entry["speaker"] and char.get("outfit"):
                return char["outfit"]
        break
    return ""


def main() -> int:
    args = parse_args()

    episode = lib.resolve_episode(args.episode, lock=True)
    config = lib.load_json(episode / "episode.yaml")
    script = lib.normalize_script(lib.load_json(episode / "script.json"))
    board = lib.load_json(episode / "storyboard.json").get("shots", [])

    if not script:
        raise SystemExit("script.json 为空，先写台词再准备")
    if not board:
        raise SystemExit("storyboard.json 还没有镜头")

    fps = int(config.get("fps", 30))
    timing_cfg = {**lib.DEFAULT_TIMING, **(config.get("timing") or {})}
    character_ids = list(config.get("characters") or [])
    if not character_ids:
        raise SystemExit("episode.yaml 的 characters 为空")

    characters: dict[str, dict] = {}
    warnings: list[str] = []
    for cid in character_ids:
        char = lib.read_character(cid)
        if not char["voice"].get("provider"):
            raise SystemExit(f"角色 {cid} 的 profile 没有配置 voice.provider")
        characters[cid] = char

    for line in script:
        if line["speaker"] not in characters:
            raise SystemExit(f"台词 {line['id']} 的说话人 {line['speaker']!r} 不在 episode.characters 中")

    line_outfits: dict[str, str] = {}
    for line in script:
        outfit = outfit_for_line(line, board) or characters[line["speaker"]]["default_outfit"]
        if outfit not in characters[line["speaker"]]["outfits"]:
            raise SystemExit(f"台词 {line['id']} 引用了不存在的服装 {outfit!r}")
        line_outfits[line["id"]] = outfit

    timed, total_frames, providers = build_timing(
        script,
        characters,
        line_outfits,
        episode,
        fps,
        timing_cfg,
        args.reuse_audio,
        args.voice_timeout,
        args.voice_fallback,
    )
    scenes: dict[tuple[str, str | None], dict] = {}
    shots, total_frames, line_shifts = build_shots(
        board,
        timed,
        timing_cfg,
        scenes,
        {cid: char["default_outfit"] for cid, char in characters.items()},
        config.get("transitions"),
    )
    # Transitions push every line after the cut later; timing.json is the
    # readable absolute timeline, so it carries the same padding as scene.json.
    for line in timed:
        line["start"] += line_shifts.get(line["id"], 0)

    raws = episode / "raws"
    (raws / "images").mkdir(parents=True, exist_ok=True)

    # Blue Archive UI kit sound effects. See data/ui/manifest.json for provenance.
    default_ui = {
        "kit": "blue-archive",
        "sfx": {"click": "click", "select": "select", "hover": "hover"},
        "lineClick": True,
        "lineClickVolume": 0.14,
    }
    raw_ui_cfg = config.get("ui") or {}
    ui_cfg = {**default_ui, **raw_ui_cfg}
    ui_cfg["sfx"] = {**default_ui["sfx"], **(raw_ui_cfg.get("sfx") or {})}
    ui_sfx: dict[str, str] = {}
    ui_sfx_dir = lib.ASSETS / "data" / "ui" / "sfx"
    raw_ui_dir = raws / "audio" / "ui"
    for key, name in ui_cfg["sfx"].items():
        if not name:
            continue
        src = ui_sfx_dir / f"{name}.wav"
        if not src.is_file():
            raise SystemExit(f"ui.sfx.{key} 指向的音效不存在：{src}")
        raw_ui_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, raw_ui_dir / src.name)
        ui_sfx[key] = f"audio/ui/{src.name}"

    # Background music is declared in episode.yaml and copied into the snapshot.
    bgm_cfg = config.get("bgm")
    scene_bgm = None
    if bgm_cfg:
        bgm_file = bgm_cfg.get("file")
        if not bgm_file:
            raise SystemExit("bgm 缺少 file")
        bgm_src = (lib.ASSETS / bgm_file).resolve()
        if not bgm_src.is_file():
            bgm_src = (episode / bgm_file).resolve()
        if not bgm_src.is_file():
            raise SystemExit(f"bgm.file 指向的音频不存在：{bgm_file}")
        bgm_dir = raws / "audio"
        bgm_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bgm_src, bgm_dir / bgm_src.name)
        scene_bgm = {
            "src": f"audio/{bgm_src.name}",
            "volume": float(bgm_cfg.get("volume", 0.15)),
            "loop": bool(bgm_cfg.get("loop", True)),
            "fadeInFrames": int(bgm_cfg.get("fadeInFrames", 45)),
            "fadeOutFrames": int(bgm_cfg.get("fadeOutFrames", 75)),
        }

    # Scene backgrounds are supplied by the owner; copy them into the episode snapshot.
    seen_scenes: set[int] = set()
    for shot in shots:
        scene_def = shot.get("scene")
        if not scene_def or id(scene_def) in seen_scenes:
            continue
        seen_scenes.add(id(scene_def))
        source = scene_def.pop("image_source", "")
        scene_def.pop("image_ref", None)
        key = f"{scene_def['id']}/{scene_def['variant']}"
        if source and Path(source).is_file():
            src = Path(source)
            dst = raws / "images" / f"scene-{scene_def['id']}-{scene_def['variant']}{src.suffix}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            scene_def["image"] = f"images/{dst.name}"
        else:
            scene_def["image"] = None
            warnings.append(f"{key}：背景图待提供，渲染先用场景 profile 的中性底色")

    # Snapshot every (character, outfit, expression) actually used, plus each default.
    used: set[tuple[str, str, str]] = set()
    for line in timed:
        used.add((line["speaker"], line["outfit"], line["emotion"]))
    for shot in shots:
        for entry in shot["characters"]:
            used.add((entry["id"], entry["outfit"], entry["emotion"]))
    for cid, char in characters.items():
        used.add((cid, char["default_outfit"], "default"))

    scene_outfits: dict[str, dict[str, dict]] = {cid: {} for cid in characters}
    for cid, outfit_id, expression in sorted(used):
        bucket = scene_outfits[cid].setdefault(outfit_id, {"sprites": {}, "fallbacks": set()})
        relative = copy_sprite(
            characters[cid], outfit_id, expression, raws, warnings, bucket["fallbacks"]
        )
        bucket["sprites"][expression] = relative
    # Always include the default outfit so the renderer can fall back, and give
    # every used outfit a `default` sprite because the template resolves unknown
    # expressions with `sprites[emotion] || sprites.default`.
    for cid, char in characters.items():
        default_id = char["default_outfit"]
        scene_outfits[cid].setdefault(default_id, {"sprites": {}, "fallbacks": set()})
        for outfit_id, bucket in scene_outfits[cid].items():
            if "default" not in bucket["sprites"]:
                bucket["sprites"]["default"] = copy_sprite(
                    characters[cid], outfit_id, "default", raws, warnings, bucket["fallbacks"]
                )

    intro_cfg = config.get("intro")
    intro = None
    if intro_cfg:
        intro = {
            "durationInFrames": int(intro_cfg.get("durationInFrames", timing_cfg["intro_frames"])),
            "kicker": intro_cfg.get("kicker", ""),
            "title": intro_cfg.get("title", config.get("title", "")),
            "subtitle": intro_cfg.get("subtitle", ""),
        }
        if timed[0]["start"] < intro["durationInFrames"]:
            raise SystemExit("intro 时长超过了第一句台词的开始时间")

    scene = {
        "schema_version": 2,
        "episode": {
            "id": config["id"],
            "title": config.get("title", ""),
            "template": config.get("template", "blue-archive"),
            "width": int(config.get("width", 1280)),
            "height": int(config.get("height", 720)),
            "fps": fps,
            "durationInFrames": total_frames,
            "style": config.get("style", {}),
            "subtitle": {**lib.DEFAULT_SUBTITLE, **(config.get("subtitle") or {})},
        },
        "characters": {
            cid: {
                "name": characters[cid]["profile"].get("name", cid),
                "color": characters[cid]["profile"].get("color", "#c44b82"),
                "club": (characters[cid]["profile"].get("persona") or {}).get("club", ""),
                "school": (characters[cid]["profile"].get("persona") or {}).get("school", ""),
                "default_outfit": characters[cid]["default_outfit"],
                "voice": {
                    "provider": characters[cid]["voice"].get("provider", ""),
                    "model": characters[cid]["voice"].get("model", ""),
                    "voice_id": characters[cid]["voice"].get("voice_id", ""),
                },
                "outfits": {
                    outfit_id: {
                        "name": characters[cid]["outfits"][outfit_id]["name"],
                        "sprites": bucket["sprites"],
                        "fallbacks": sorted(bucket["fallbacks"]),
                    }
                    for outfit_id, bucket in sorted(scene_outfits[cid].items())
                },
            }
            for cid in characters
        },
        "intro": intro,
        "bgm": scene_bgm,
        "ui": {
            "kit": ui_cfg["kit"],
            "sfx": ui_sfx,
            "lineClick": bool(ui_cfg["lineClick"]),
            "lineClickVolume": float(ui_cfg["lineClickVolume"]),
        },
        "shots": shots,
        "warnings": warnings,
    }

    timing = {
        "fps": fps,
        "durationInFrames": total_frames,
        "providers": providers,
        "lines": [
            {
                "id": line["id"],
                "speaker": line["speaker"],
                "outfit": line["outfit"],
                "emotion": line["emotion"],
                "text": line["text"],
                "start": line["start"],
                "frames": line["frames"],
                "seconds": line["seconds"],
                "audio": line["audio"],
                "tts": line["tts"],
            }
            for line in timed
        ],
        "warnings": warnings,
    }
    lib.write_json(episode / "audio" / "timing.json", timing)
    lib.write_json(episode / "project" / "scene.json", scene)

    locked = []
    for path in sorted(raws.rglob("*")):
        if path.is_file():
            locked.append(
                {
                    "path": str(path.relative_to(episode)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    lib.write_json(episode / "assets.lock.json", {"assets": locked})

    print(f"准备完成：{config['id']}")
    print(f"  时长：{total_frames / fps:.2f}s / {total_frames} 帧 @ {fps}fps")
    print(f"  台词：{len(timed)} 句，镜头：{len(shots)} 个")
    print(f"  语音：{', '.join(f'{k}×{v}' for k, v in sorted(providers.items()))}")
    print(f"  scene：{episode / 'project' / 'scene.json'}")
    if warnings:
        print("  警告：")
        for warning in warnings:
            print(f"    - {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
