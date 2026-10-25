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
from sprite_coordinates import read_coordinates

BUBBLE_PRESETS = json.loads((Path(__file__).resolve().parents[1] / "templates/bubble-presets.json").read_text())

def resolve_bubble_frame(cue: dict, shot_lines: list[dict], start: int, lead: int, duration: int,
                          shot_id: str, character_id: str) -> int:
    """Content-relative bubble start. ``atLine`` aligns to a line start, ``afterLine`` to its end."""
    if cue.get("name") not in BUBBLE_PRESETS:
        raise SystemExit(f"Invalid bubble cue: {cue!r}")
    anchors = [key for key in ("startFrame", "atLine", "afterLine") if key in cue]
    if len(anchors) > 1:
        raise SystemExit(f"镜头 {shot_id} 角色 {character_id} 的气泡只能写 startFrame、atLine、afterLine 中的一个")
    offset = cue.get("offsetFrames", 0)
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise SystemExit("bubbles.offsetFrames must be an integer")
    if "atLine" in cue or "afterLine" in cue:
        field = "afterLine" if "afterLine" in cue else "atLine"
        line = next((item for item in shot_lines if item["id"] == cue[field]), None)
        if line is None:
            raise SystemExit(
                f"镜头 {shot_id} 角色 {character_id} 的 bubbles.{field}={cue[field]!r} 不在该镜头台词中"
            )
        frame = (line["from"] - start - lead) + offset
        if field == "afterLine":
            frame += line["durationInFrames"]
    else:
        if "offsetFrames" in cue:
            raise SystemExit("bubbles.offsetFrames 只能和 atLine 或 afterLine 一起用")
        frame = cue.get("startFrame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int):
            raise SystemExit(f"Invalid bubble cue: {cue!r}")
    if not (0 <= frame < duration - lead):
        raise SystemExit(f"Bubble starts outside shot {shot_id}")
    return frame


def snapshot_bubbles(shots: list[dict], raws: Path) -> None:
    """Snapshot effect media; fail instead of silently rendering a missing effect."""
    for shot in shots:
        for character in shot.get("characters", []):
            for cue in character.get("bubbles", []):
                preset = BUBBLE_PRESETS[cue["name"]]
                media = {f"image{index}": lib.ROOT / "data/effects/ba" / image
                         for index, image in enumerate(preset["images"])}
                if cue["sound"]:
                    media["audio"] = lib.ROOT / f"data/audio/sfx/SFX_Emoticon_Motion_{cue['name']}.wav"
                for field, src in media.items():
                    if not src.is_file():
                        raise SystemExit(f"Missing bubble asset: {src.name}; run fetch_bubbles.py")
                    relative = Path("effects") / src.name
                    dst = raws / relative
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    cue[field] = relative.as_posix()
                cue["images"] = [cue.pop(f"image{index}") for index in range(len(preset["images"]))]


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
    intro_hold: int = 0,
    line_gaps: dict[str, int] | None = None,
    leading_frames: int = 0,
) -> tuple[list[dict], int, dict]:
    gaps = line_gaps or {}
    audio_dir = episode / "audio"
    raws_audio = episode / "raws" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    raws_audio.mkdir(parents=True, exist_ok=True)

    # `intro_hold` is 0 when episode.yaml has no intro block, so deleting the
    # title card also drops the frames that used to sit under it.
    cursor = leading_frames + intro_hold + timing_cfg["lead_in_frames"]
    timed: list[dict] = []
    providers: dict[str, int] = {}
    for index, line in enumerate(script):
        char = characters[line["speaker"]]
        outfit_id = line_outfits.get(line["id"], char["default_outfit"])
        target = audio_dir / f"{index:03}.mp3"
        if line.get("silent"):
            # Text-only beat such as a lone "……": keep the caption, skip TTS.
            frames = max(timing_cfg["min_line_frames"], int(0.8 * fps))
            tts = {"provider": "silent", "voice_id": "", "model": "", "speed": 1.0, "fallback": False}
            providers["silent"] = providers.get("silent", 0) + 1
            timed.append(
                {
                    **line,
                    "outfit": outfit_id,
                    "start": cursor,
                    "frames": frames,
                    "seconds": 0.0,
                    "audio": "",
                    "tts": tts,
                }
            )
            cursor += frames + gaps.get(line["id"], 0)
            continue
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
        cursor += frames + gaps.get(line["id"], 0)
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
    line_gaps: dict[str, int] | None = None,
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

    # Reaction shots consume the silent gap that build_timing inserted after the
    # previous shot's last line. Their declared duration is authoritative.
    for shot in board:
        if not (shot.get("lines") or []):
            hold = int(shot.get("durationInFrames") or 0)
            if hold <= 0:
                raise SystemExit(
                    f"镜头 {shot['id']} 没有台词，必须写正整数 durationInFrames"
                )

    total = timed[-1]["start"] + timed[-1]["frames"] + timing_cfg["outro_frames"]
    total += (line_gaps or {}).get(timed[-1]["id"], 0)
    boundaries = [0]
    for index in range(1, len(board)):
        previous = board[index - 1]
        current = board[index]
        if previous.get("lines"):
            last = by_id[previous["lines"][-1]]
            previous_end = last["start"] + last["frames"]
            if current.get("lines"):
                previous_end += timing_cfg["shot_tail_frames"]
        else:
            previous_end = boundaries[index - 1] + int(previous["durationInFrames"])
        if current.get("lines") and previous.get("lines"):
            first = by_id[current["lines"][0]]
            cut = max(previous_end, first["start"] - timing_cfg["shot_cut_lead_frames"])
            cut = min(cut, first["start"])
        else:
            cut = previous_end
        boundaries.append(cut)
    last = board[-1]
    if last.get("lines"):
        last_line = by_id[last["lines"][-1]]
        end = (
            last_line["start"]
            + last_line["frames"]
            + timing_cfg["outro_frames"]
        )
        total = max(total, end)
    else:
        total = boundaries[-1] + int(last["durationInFrames"])
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
        for lid in raw.get("lines") or []:
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
                # A walk/exit can be anchored to the line that triggers it, so
                # storyboards survive voice-timing changes.
                if "atLine" in motion:
                    anchor = next(
                        (item for item in shot_lines if item["id"] == motion["atLine"]),
                        None,
                    )
                    if anchor is None:
                        raise SystemExit(
                            f"镜头 {raw['id']} 角色 {entry['id']} 的 motion.atLine={motion['atLine']!r} 不在该镜头台词中"
                        )
                    base = anchor["from"] - start + int(motion.get("offsetFrames", 0))
                    motion["startFrame"] = base
                    motion["endFrame"] = base + int(motion.get("durationInFrames", 18))
                    motion.pop("atLine", None)
                    motion.pop("offsetFrames", None)
                    motion.pop("durationInFrames", None)
                for field in ("startFrame", "endFrame"):
                    if motion.get(field) is not None:
                        motion[field] = int(motion[field]) + lead
            emotion_cues = []
            for cue in entry.get("emotionCues") or []:
                name = cue.get("emotion")
                if not name:
                    raise SystemExit(f"镜头 {raw['id']} 角色 {entry['id']} 的 emotionCues 缺少 emotion")
                cue_frame = int(cue.get("startFrame", 0)) + lead
                if not (0 <= cue_frame < duration):
                    raise SystemExit(
                        f"镜头 {raw['id']} 角色 {entry['id']} 的表情起点 {cue_frame} 超出镜头时长 {duration} 帧"
                    )
                emotion_cues.append({"emotion": name, "startFrame": cue_frame})
            actions = []
            action_names = {"jump", "hophop", "greeting", "shake", "stiff", "closeup", "falldownL", "falldownR", "hide"}
            for cue in entry.get("actions") or []:
                name = cue.get("name")
                cue_frame = cue.get("startFrame", 0)
                if name not in action_names:
                    raise SystemExit(f"Unknown character action: {name!r}")
                if isinstance(cue_frame, bool) or not isinstance(cue_frame, int):
                    raise SystemExit("actions.startFrame must be an integer")
                cue_frame += lead
                if not (lead <= cue_frame < duration):
                    raise SystemExit(f"Character action {name} starts outside shot {raw['id']}")
                actions.append({"name": name, "startFrame": cue_frame})
            bubbles = []
            for cue in entry.get("bubbles") or []:
                frame = resolve_bubble_frame(cue, shot_lines, start, lead, duration, raw["id"], entry["id"])
                if not isinstance(cue.get("sound", True), bool):
                    raise SystemExit("bubbles.sound must be boolean")
                # Presets own placement, scale, and duration. Authoring fields x/y/scale/duration are ignored.
                bubbles.append({"name": cue["name"], "startFrame": frame + lead, "sound": cue.get("sound", True)})
            characters.append(
                {
                    "id": entry["id"],
                    "outfit": entry.get("outfit") or default_outfits.get(entry["id"]),
                    "x": entry.get("x", 0.5),
                    "bottom": entry.get("bottom", lib.DEFAULT_CHARACTER_BOTTOM),
                    "height": entry.get("height", lib.DEFAULT_CHARACTER_HEIGHT),
                    "scale": entry.get("scale", 1.0),
                    "entrance": entry.get("entrance", "fade-in"),
                    "exit": entry.get("exit", "none"),
                    "emotion": entry.get("emotion", "default"),
                    "holdEmotion": bool(entry.get("holdEmotion", False)),
                    "emotionCues": emotion_cues,
                    "actions": actions,
                    "bubbles": bubbles,
                    "facing": facing,
                    "turns": turns,
                    "motion": motion,
                    "label": entry.get("label"),
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
                "focus": raw.get("focus"),
                "monologue": raw.get("monologue"),
                "voteTags": raw.get("voteTags"),
                "systemVoice": raw.get("systemVoice"),
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


def resolve_audio_source(value: str, episode: Path) -> Path:
    source = Path(value)
    if not source.is_absolute():
        source = lib.ROOT / value
        if not source.is_file():
            source = episode / value
    if not source.is_file():
        raise SystemExit(f"音频文件不存在：{value}")
    return source


def prepare_monologues(board: list[dict], characters: dict, episode: Path, fps: int,
                       reuse_audio: bool, timeout: int, allow_fallback: bool) -> dict[str, Path]:
    files = {}
    for shot in board:
        mono = shot.get("monologue")
        if not mono:
            continue
        speaker = mono.get("speaker")
        if speaker not in characters:
            raise SystemExit(f"镜头 {shot['id']} 的 monologue.speaker={speaker!r} 不在 episode.characters 中")
        if mono.get("audio"):
            target = resolve_audio_source(mono["audio"], episode)
        else:
            target = episode / "audio" / f"mono-{shot['id']}.mp3"
            if not (reuse_audio and target.is_file()):
                voice.synthesize_line(mono.get("text", ""), characters[speaker]["voice"],
                                      target, timeout, allow_fallback)
        needed = math.ceil(lib.probe_duration(target) * fps) + 12
        shot["durationInFrames"] = max(int(shot.get("durationInFrames") or 0), needed)
        files[shot["id"]] = target
    return files


def reaction_gaps(board: list[dict]) -> tuple[int, dict[str, int]]:
    leading = 0
    gaps = {}
    last_line = None
    for shot in board:
        if shot.get("lines"):
            last_line = shot["lines"][-1]
        elif last_line is None:
            leading += int(shot.get("durationInFrames") or 0)
        else:
            gaps[last_line] = gaps.get(last_line, 0) + int(shot.get("durationInFrames") or 0)
    return leading, gaps


def snapshot_shot_audio(shots: list[dict], monologue_files: dict[str, Path],
                        episode: Path, raws: Path) -> None:
    for index, shot in enumerate(shots):
        sources = []
        if shot.get("systemVoice"):
            sources.append(("system", resolve_audio_source(shot["systemVoice"], episode)))
        if shot.get("monologue"):
            sources.append(("monologue", monologue_files[shot["id"]]))
        for kind, source in sources:
            relative = f"audio/{kind}/{index:03d}{source.suffix}"
            target = raws / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            if kind == "system":
                shot["systemVoice"] = relative
            else:
                shot["monologue"]["audio"] = relative


def prepare_bgm(bgm_cfg: dict | None, shots: list[dict], episode: Path, raws: Path) -> dict | None:
    """Resolve BGM timing and snapshot each track without sharing dialogue paths."""
    if not bgm_cfg:
        return None
    bgm_file = bgm_cfg.get("file")
    if not bgm_file:
        raise SystemExit("bgm 缺少 file")
    bgm_src = (lib.ROOT / bgm_file).resolve()
    if not bgm_src.is_file():
        bgm_src = (episode / bgm_file).resolve()
    if not bgm_src.is_file():
        raise SystemExit(f"bgm.file 指向的音频不存在：{bgm_file}")
    bgm_dir = raws / "audio" / "bgm"
    bgm_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"base{bgm_src.suffix}"
    shutil.copy2(bgm_src, bgm_dir / base_name)

    shot_index = {shot["id"]: index for index, shot in enumerate(shots)}

    def bgm_range(
        from_id: str,
        to_id: str | None,
        at_line: str | None = None,
        offset_frames: int = 0,
    ) -> tuple[int, int]:
        if from_id not in shot_index:
            raise SystemExit(f"bgm 引用了不存在的镜头：{from_id}")
        target = to_id or from_id
        if target not in shot_index:
            raise SystemExit(f"bgm 引用了不存在的镜头：{target}")
        first = shot_index[from_id]
        last = shot_index[target]
        if last < first:
            raise SystemExit(f"bgm 的镜头范围反了：{from_id} → {target}")
        start = int(shots[first]["from"])
        if at_line:
            anchor = next(
                (line for line in shots[first].get("lines") or [] if line["id"] == at_line),
                None,
            )
            if anchor is None:
                raise SystemExit(f"bgm 的 atLine={at_line!r} 不在镜头 {from_id} 中")
            start = int(anchor["from"]) + int(offset_frames)
        end = int(shots[last]["from"]) + int(shots[last]["durationInFrames"])
        if not 0 <= start < end:
            raise SystemExit(f"bgm 的起点 {start} 超出镜头范围 {from_id} → {target}")
        return start, end - start

    mute_ranges = []
    for item in bgm_cfg.get("mute") or []:
        start, length = bgm_range(
            item["from"],
            item.get("to"),
            item.get("atLine"),
            int(item.get("offsetFrames", 0)),
        )
        mute_ranges.append({"from": start, "durationInFrames": length})

    cues = []
    for index, item in enumerate(bgm_cfg.get("cues") or []):
        cue_file = item.get("file")
        if not cue_file:
            raise SystemExit("bgm.cues 缺少 file")
        cue_src = (lib.ROOT / cue_file).resolve()
        if not cue_src.is_file():
            cue_src = (episode / cue_file).resolve()
        if not cue_src.is_file():
            raise SystemExit(f"bgm.cues 指向的音频不存在：{cue_file}")
        cue_name = f"cue-{index:03d}{cue_src.suffix}"
        shutil.copy2(cue_src, bgm_dir / cue_name)
        start, length = bgm_range(
            item["from"],
            item.get("to"),
            item.get("atLine"),
            int(item.get("offsetFrames", 0)),
        )
        cues.append(
            {
                "from": start,
                "durationInFrames": length,
                "src": f"audio/bgm/{cue_name}",
                "volume": float(item.get("volume", 0.5)),
                "loop": bool(item.get("loop", True)),
            }
        )

    scene_bgm = {
        "src": f"audio/bgm/{base_name}",
        "volume": float(bgm_cfg.get("volume", 0.15)),
        "loop": bool(bgm_cfg.get("loop", True)),
        "fadeInFrames": int(bgm_cfg.get("fadeInFrames", 45)),
        "fadeOutFrames": int(bgm_cfg.get("fadeOutFrames", 75)),
        "muteRanges": mute_ranges,
        "cues": cues,
        "resumeFadeFrames": int(bgm_cfg.get("resumeFadeFrames", 0)),
    }

    return scene_bgm


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

    try:
        intro_hold = lib.intro_hold_frames(config, timing_cfg)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    monologue_files = prepare_monologues(
        board, characters, episode, fps, args.reuse_audio,
        args.voice_timeout, args.voice_fallback,
    )
    leading_frames, line_gaps = reaction_gaps(board)

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
        intro_hold,
        line_gaps,
        leading_frames,
    )
    scenes: dict[tuple[str, str | None], dict] = {}
    shots, total_frames, line_shifts = build_shots(
        board,
        timed,
        timing_cfg,
        scenes,
        {cid: char["default_outfit"] for cid, char in characters.items()},
        config.get("transitions"),
        line_gaps,
    )
    # Transitions push every line after the cut later; timing.json is the
    # readable absolute timeline, so it carries the same padding as scene.json.
    for line in timed:
        line["start"] += line_shifts.get(line["id"], 0)

    raws = episode / "raws"
    (raws / "images").mkdir(parents=True, exist_ok=True)
    snapshot_bubbles(shots, raws)

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
    ui_sfx_dir = lib.ROOT / "data" / "ui" / "sfx"
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

    scene_bgm = prepare_bgm(config.get("bgm"), shots, episode, raws)

    snapshot_shot_audio(shots, monologue_files, episode, raws)

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
            for cue in entry.get("emotionCues") or []:
                used.add((entry["id"], entry["outfit"], cue["emotion"]))
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
    for shot in shots:
        for entry in shot["characters"]:
            if not entry.get("bubbles"):
                continue
            cid, oid = entry["id"], entry["outfit"]
            char = characters[cid]
            skeleton = char["profile"]["outfits"][oid].get("spine")
            if not skeleton:
                raise SystemExit(f"{cid}/{oid}: bubbles require a matching outfit.spine export; refusing guessed coordinates")
            scene_outfits[cid][oid]["spineBounds"] = read_coordinates(
                char["dir"] / skeleton, char["outfits"][oid]["sprites"]["default"]["path"])
    intro = None
    if intro_cfg:
        intro = {
            "durationInFrames": intro_hold,
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
            "template": config.get("template", "official"),
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
                        "spineBounds": bucket.get("spineBounds"),
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
