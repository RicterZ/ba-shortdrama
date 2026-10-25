#!/usr/bin/env python3
"""Validate episode data, timing, assets and rendered output.

Examples:
    uv run python scripts/validate.py --episode 002-hidden-ending
    uv run python scripts/validate.py --all
"""
from __future__ import annotations

import argparse
import hashlib
import math
import sys
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


class Report:
    def __init__(self, episode: Path):
        self.episode = episode
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_schema(report: Report, name: str, data, schema_name: str) -> bool:
    schema = lib.load_json(lib.SCHEMAS / f"{schema_name}.json")
    try:
        jsonschema.validate(data, schema)
        return True
    except jsonschema.ValidationError as exc:
        report.error(f"{name} 不符合 {schema_name} schema：{exc.message}")
        return False


def check_characters(report: Report, config: dict) -> dict[str, dict]:
    characters: dict[str, dict] = {}
    ids = config.get("characters") or []
    if not ids:
        report.error("episode.yaml 没有配置 characters")
    for cid in ids:
        try:
            char = lib.read_character(cid)
        except (FileNotFoundError, ValueError) as exc:
            report.error(str(exc))
            continue
        characters[cid] = char
        profile = char["profile"]
        validate_schema(report, f"{cid}/profile.yaml", profile, "profile")

        for outfit_id, outfit in char["outfits"].items():
            for expression, meta in outfit["sprites"].items():
                path = meta["path"]
                if not path.is_file():
                    report.error(f"{cid}/{outfit_id}/{expression} 立绘不存在：{path}")
                    continue
                if meta.get("sha256"):
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest != meta["sha256"]:
                        report.error(f"{cid}/{outfit_id}/{expression} 立绘哈希与 profile 不一致")

        voice = char["voice"]
        provider = voice.get("provider")
        if provider not in ("fish-audio", "edge-tts", "vocu"):
            report.error(f"{cid} 的 voice.provider 不支持：{provider!r}")
        if not voice.get("voice_id"):
            report.error(f"{cid} 的 voice.voice_id 为空")
        if provider == "fish-audio":
            if not voice.get("model"):
                report.error(f"{cid} 使用 fish-audio 但没有配置 model")
            key_env = voice.get("api_key_env") or "FISH_AUDIO_API_KEY"
            if not lib.env_value(key_env):
                report.warn(f"{cid} 缺少 {key_env}（local/.env），prepare 会失败")
        if provider == "vocu":
            key_env = voice.get("api_key_env") or "VOCU_API_KEY"
            if not lib.env_value(key_env):
                report.warn(f"{cid} missing {key_env} (local/.env); prepare will fail")
            if voice.get("format", "mp3") != "mp3":
                report.error(f"{cid}: vocu supports mp3 only")
        if not voice.get("fallback"):
            report.warn(f"{cid} 没有配置语音 fallback")

        if profile.get("missing"):
            report.warn(f"{cid} 声明缺失素材：{'；'.join(profile['missing'])}")
    return characters


def check_script_and_board(
    report: Report, config: dict, script_raw: list, board: dict, characters: dict
) -> tuple[list[dict], list[dict]]:
    if not isinstance(script_raw, list):
        report.error("script.json 必须是数组")
        return [], []
    if not script_raw:
        report.error("script.json 为空，先写台词")
        return [], []

    try:
        script = lib.normalize_script(script_raw)
    except ValueError as exc:
        report.error(str(exc))
        return [], []

    subtitle = {**lib.DEFAULT_SUBTITLE, **(config.get("subtitle") or {})}
    max_chars = int(subtitle["max_chars_per_line"])
    max_lines = int(subtitle["max_lines"])

    transitions_cfg = config.get("transitions")
    if transitions_cfg is not None:
        if not isinstance(transitions_cfg, dict):
            report.error("episode.yaml 的 transitions 必须是对象")
        else:
            on = transitions_cfg.get("on", lib.DEFAULT_TRANSITIONS["on"])
            if on not in ("scene-change", "every-cut", "none"):
                report.error(
                    f"episode.yaml 的 transitions.on 不支持 {on!r}，可选：scene-change / every-cut / none"
                )
            try:
                lib.parse_transition({}, transitions_cfg)
            except ValueError as exc:
                report.error(f"episode.yaml 的 transitions 配置无效：{exc}")

    for line in script:
        if line["speaker"] not in characters:
            report.error(f"台词 {line['id']} 的说话人 {line['speaker']!r} 不在 episode.characters 中")
        lines_needed = lib.wrapped_lines(line["text"], max_chars)
        if lines_needed > max_lines:
            report.error(
                f"台词 {line['id']} 约需 {lines_needed} 行字幕，超过上限 {max_lines} 行（每行 {max_chars} 字）：{line['text']}"
            )
        if lib.text_units(line["text"]) > max_chars * max_lines:
            report.error(f"台词 {line['id']} 过长，字幕会溢出安全区")
        for field in ("speaker", "text"):
            if not str(line[field]).strip():
                report.error(f"台词 {line['id']} 的 {field} 为空")

    shots_raw = board.get("shots") or []
    if not shots_raw:
        report.error("storyboard.json 还没有镜头")
        return script, []

    shot_ids = set()
    checked_scenes: set[str] = set()
    flat = []
    for index, shot in enumerate(shots_raw):
        sid = shot.get("id")
        if not sid:
            report.error(f"第 {index + 1} 个镜头缺少 id")
            continue
        if sid in shot_ids:
            report.error(f"镜头 id 重复：{sid}")
        shot_ids.add(sid)
        line_ids = shot.get("lines") or []
        if not line_ids and not shot.get("durationInFrames"):
            report.error(f"镜头 {sid} 没有引用台词，也没有 durationInFrames")
        if not line_ids and shot.get("durationInFrames"):
            if int(shot["durationInFrames"]) <= 0:
                report.error(f"镜头 {sid} 的 durationInFrames 必须为正整数")
        flat.extend(line_ids)
        for entry in shot.get("characters") or []:
            cid = entry.get("id")
            if cid not in characters:
                report.error(f"镜头 {sid} 引用了未配置的角色：{cid!r}")
                continue
            outfit = entry.get("outfit") or characters[cid]["default_outfit"]
            if outfit not in characters[cid]["outfits"]:
                report.error(f"镜头 {sid} 的角色 {cid} 引用了不存在的服装 {outfit!r}")
            if not 0.0 <= float(entry.get("x", 0.5)) <= 1.0:
                report.error(f"镜头 {sid} 角色 {cid} 的 x 必须在 0 到 1 之间")
            if not 0.0 <= float(entry.get("height", lib.DEFAULT_CHARACTER_HEIGHT)) <= 3.0:
                report.error(f"镜头 {sid} 角色 {cid} 的 height 超出合理范围")

        scene_ref = shot.get("scene")
        if scene_ref:
            scene_id = scene_ref if isinstance(scene_ref, str) else scene_ref.get("id")
            variant = None if isinstance(scene_ref, str) else scene_ref.get("variant")
            try:
                scene_profile = lib.read_scene(scene_id, variant)
            except (FileNotFoundError, ValueError) as exc:
                report.error(f"镜头 {sid} 的场景配置无效：{exc}")
            else:
                if f"scene:{scene_id}" not in checked_scenes:
                    checked_scenes.add(f"scene:{scene_id}")
                    path = lib.SCENES / scene_id / "scene.yaml"
                    validate_schema(report, f"scenes/{scene_id}/scene.yaml", lib.load_json(path), "scene")

        transition = shot.get("transition")
        if transition is not None:
            if index == 0:
                report.error(f"镜头 {sid} 是第一个镜头，不能声明转场")
            try:
                lib.parse_transition(transition, lib.transition_defaults(transition, transitions_cfg))
            except ValueError as exc:
                report.error(f"镜头 {sid} 的转场无效：{exc}")

        choices = shot.get("choices")
        if choices:
            options = choices.get("options") or []
            if len(options) < 2 or not all(isinstance(item, str) and item.strip() for item in options):
                report.error(f"镜头 {sid} 的 choices 至少需要两个非空选项")
            selected = choices.get("selected", 0)
            if not isinstance(selected, int) or not 0 <= selected < len(options):
                report.error(f"镜头 {sid} 的 choices.selected 超出选项范围")
            for field in ("fromFrame", "selectFrame", "hideFrame"):
                value = choices.get(field)
                if value is not None and (not isinstance(value, int) or value < 0):
                    report.error(f"镜头 {sid} 的 choices.{field} 必须是非负整数")
            select = choices.get("selectFrame")
            hide = choices.get("hideFrame")
            if isinstance(select, int) and isinstance(hide, int) and hide <= select:
                report.error(f"镜头 {sid} 的 choices.hideFrame 必须晚于 selectFrame")

        for button in shot.get("buttons") or []:
            if not isinstance(button.get("label"), str) or not button["label"].strip():
                report.error(f"镜头 {sid} 有一个没有 label 的按钮")
            press = button.get("pressFrame")
            if press is not None and (not isinstance(press, int) or press < 0):
                report.error(f"镜头 {sid} 的按钮 {button.get('label')!r} pressFrame 必须是非负整数")
            for key in ("x", "y"):
                value = button.get(key)
                if value is not None and not 0 <= float(value) <= 1:
                    report.error(f"镜头 {sid} 的按钮 {button.get('label')!r} {key} 必须在 0..1")

        if not shot.get("characters"):
            report.warn(f"镜头 {sid} 没有角色，画面上只有背景")

    expected = [line["id"] for line in script]
    if flat != expected:
        report.error(
            "storyboard 的台词引用与 script.json 不一致（要求每个台词恰好出现一次且顺序一致）：\n"
            f"    storyboard: {flat}\n    script:     {expected}"
        )
    return script, shots_raw


def check_timing(
    report: Report, episode: Path, config: dict, script: list[dict], scene: dict | None
) -> dict | None:
    timing_path = episode / "audio" / "timing.json"
    if not timing_path.is_file():
        report.warn("尚未生成 audio/timing.json，先运行 prepare.py")
        return None
    timing = lib.load_json(timing_path)
    fps = int(config.get("fps", 30))
    timing_cfg = {**lib.DEFAULT_TIMING, **(config.get("timing") or {})}
    tail = int(timing_cfg["tail_frames"])

    lines = timing.get("lines") or []
    if [line.get("id") for line in lines] != [line["id"] for line in script]:
        report.error("timing.json 的台词顺序与 script.json 不一致")
        return timing

    raws = episode / "raws"
    previous_end = -1
    for line in lines:
        start = int(line.get("start", -1))
        frames = int(line.get("frames", 0))
        audio = raws / str(line.get("audio", ""))
        if start < 0 or frames <= 0:
            report.error(f"台词 {line.get('id')} 的 start/frames 非法")
            continue
        if start < previous_end:
            report.error(f"台词 {line.get('id')} 与上一句时间重叠")
        previous_end = start + frames
        if not line.get("audio"):
            continue
        if not audio.is_file():
            report.error(f"台词 {line.get('id')} 的音频不存在：{audio}")
            continue
        try:
            seconds = lib.probe_duration(audio)
        except Exception as exc:  # noqa: BLE001
            report.error(f"无法读取音频 {audio}：{exc}")
            continue
        minimum = math.ceil(seconds * fps)
        if frames < minimum:
            report.error(f"台词 {line.get('id')} 只有 {frames} 帧，短于音频所需的 {minimum} 帧")
        elif frames > minimum + tail + 2:
            report.warn(f"台词 {line.get('id')} 静音尾巴偏长（{frames - minimum} 帧）")
        if abs(float(line.get("seconds", seconds)) - seconds) > 0.15:
            report.warn(f"台词 {line.get('id')} 记录的时长与音频实测不一致")

    try:
        intro_hold = lib.intro_hold_frames(config, timing_cfg)
    except ValueError as exc:
        report.error(str(exc))
        intro_hold = 0
    if lines and int(lines[0]["start"]) < intro_hold:
        report.error("第一句台词开始时间早于 intro 结束时间")

    if scene:
        if int(scene.get("episode", {}).get("durationInFrames", -1)) != int(timing["durationInFrames"]):
            report.error("scene.json 与 timing.json 的总时长不一致")
        if int(timing["durationInFrames"]) <= previous_end:
            report.error("总时长不足以容纳最后一句台词")
    return timing


def check_scene(
    report: Report, episode: Path, characters: dict, script: list[dict], scene: dict | None, timing: dict | None
) -> None:
    if scene is None:
        return
    raws = episode / "raws"
    shots = scene.get("shots") or []
    if not shots:
        report.error("scene.json 没有镜头")
        return

    expected_end = 0
    previous_duration = 0
    seen_lines: list[str] = []
    for index, shot in enumerate(shots):
        start = int(shot["from"])
        duration = int(shot["durationInFrames"])
        transition = shot.get("transition") or {}
        if not isinstance(transition, dict):
            report.error(f"镜头 {shot.get('id')} 的 transition 必须是对象")
            transition = {}
        overlap = int(transition.get("durationInFrames") or 0)
        if transition:
            if transition.get("type") not in lib.TRANSITION_TYPES:
                report.error(f"镜头 {shot.get('id')} 使用了未知转场 {transition.get('type')!r}")
            if overlap <= 0:
                report.error(f"镜头 {shot.get('id')} 的转场时长必须为正")
            elif overlap >= duration or overlap >= previous_duration:
                report.error(
                    f"镜头 {shot.get('id')} 的转场 {overlap} 帧必须短于相邻镜头"
                    f"（上一镜头 {previous_duration} 帧、本镜头 {duration} 帧）"
                )
        if index == 0:
            if start != 0:
                report.error(f"镜头 {shot.get('id')} 起点 {start} 必须是 0")
        elif start != expected_end - overlap:
            report.error(
                f"镜头 {shot.get('id')} 起点 {start} 与上一镜头结束 {expected_end} "
                f"减去 {overlap} 帧转场后不连续"
            )
        expected_end = start + duration
        previous_duration = duration
        for entry in shot.get("characters") or []:
            cid = entry.get("id")
            if cid not in scene.get("characters", {}):
                report.error(f"镜头 {shot.get('id')} 引用了 scene 中不存在的角色 {cid}")
        for line in shot.get("lines") or []:
            seen_lines.append(line.get("id"))
            if int(line.get("from", 0)) < start + overlap:
                report.error(f"台词 {line.get('id')} 在镜头 {shot.get('id')} 的转场窗口内开始")
            audio = raws / str(line.get("audio", ""))
            if line.get("audio") and not audio.is_file():
                report.error(f"台词 {line.get('id')} 的音频缺失：{audio}")

        choices = shot.get("choices")
        if choices:
            from_frame = int(choices.get("fromFrame") or 0)
            hide = choices.get("hideFrame")
            if from_frame >= duration:
                report.error(f"镜头 {shot.get('id')} 的 choices.fromFrame 超出镜头时长")
            if hide is not None and int(hide) > duration:
                report.error(f"镜头 {shot.get('id')} 的 choices.hideFrame 超出镜头时长")
        for button in shot.get("buttons") or []:
            press = button.get("pressFrame")
            if press is not None and int(press) >= duration:
                report.error(f"镜头 {shot.get('id')} 的按钮 {button.get('label')!r} pressFrame 超出镜头时长")

    if expected_end != int(scene["episode"]["durationInFrames"]):
        report.error("scene.json 的镜头时间轴与总时长不一致")
    if [lid for lid in seen_lines] != [line["id"] for line in script]:
        report.error("scene.json 的台词覆盖与 script.json 不一致")

    ui = scene.get("ui") or {}
    for key, relative in sorted((ui.get("sfx") or {}).items()):
        if not (raws / str(relative)).is_file():
            report.error(f"scene.ui.sfx.{key} 的音效文件不存在：{relative}")

    bgm = scene.get("bgm")
    if bgm:
        relative = bgm.get("src")
        if not relative or not (raws / str(relative)).is_file():
            report.error(f"scene.bgm 的音频文件不存在：{relative}")

    for cid, data in (scene.get("characters") or {}).items():
        outfits = data.get("outfits") or {}
        if not outfits:
            report.error(f"scene 中角色 {cid} 没有服装")
            continue
        if data.get("default_outfit") not in outfits:
            report.error(f"scene 中角色 {cid} 的 default_outfit 不存在")
        for outfit_id, outfit in outfits.items():
            sprites = outfit.get("sprites") or {}
            if not sprites:
                report.error(f"scene 中角色 {cid}/{outfit_id} 没有立绘")
            for expression, relative in sprites.items():
                if not (raws / relative).is_file():
                    report.error(f"角色 {cid}/{outfit_id} 的表情 {expression} 引用文件不存在：{relative}")
            if "default" not in sprites:
                report.error(f"scene 中角色 {cid}/{outfit_id} 没有 default 立绘")
            for expression in outfit.get("fallbacks") or []:
                if expression not in sprites:
                    report.error(f"角色 {cid}/{outfit_id} 的 fallback 记录 {expression} 没有对应立绘")
        for entry in [e for shot in shots for e in shot.get("characters", []) if e.get("id") == cid]:
            if entry.get("outfit") not in outfits:
                report.error(f"scene 中角色 {cid} 使用了不存在的服装 {entry.get('outfit')!r}")

    for shot in shots:
        if shot.get("scene") is None and not shot.get("background"):
            report.error(f"镜头 {shot.get('id')} 既没有场景也没有背景")
        scene_def = shot.get("scene")
        if scene_def:
            if scene_def.get("renderer") not in ("image-stage",):
                report.error(f"镜头 {shot.get('id')} 使用了未知渲染器 {scene_def.get('renderer')!r}")
            for key in ("wallTop", "wallBottom", "floor", "accent"):
                if key not in (scene_def.get("palette") or {}):
                    report.error(f"镜头 {shot.get('id')} 的场景缺少调色板字段 {key}")
            image = scene_def.get("image")
            if image:
                if not (raws / image).is_file():
                    report.error(f"镜头 {shot.get('id')} 的场景背景图不存在：{image}")
            else:
                report.warn(
                    f"镜头 {shot.get('id')} 的场景 {scene_def.get('id')}/{scene_def.get('variant')} 还没有背景图"
                    "（等待提供，当前用中性底色）"
                )

    if timing:
        for line in timing.get("lines") or []:
            if line.get("audio") and not (raws / str(line.get("audio", ""))).is_file():
                report.error(f"timing 中台词 {line.get('id')} 的音频缺失")


def check_lock(report: Report, episode: Path) -> None:
    lock_path = episode / "assets.lock.json"
    if not lock_path.is_file():
        report.warn("缺少 assets.lock.json，先运行 prepare.py")
        return
    lock = lib.load_json(lock_path)
    recorded = {item["path"]: item["sha256"] for item in lock.get("assets", [])}
    actual = {
        str(path.relative_to(episode)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((episode / "raws").rglob("*"))
        if path.is_file()
    }
    missing = sorted(set(recorded) - set(actual))
    extra = sorted(set(actual) - set(recorded))
    if missing:
        report.error(f"assets.lock.json 记录了不存在的文件：{missing}")
    if extra:
        report.error(f"raws/ 有未锁定的文件（重新运行 prepare.py）：{extra}")
    for path in sorted(set(recorded) & set(actual)):
        if recorded[path] != actual[path]:
            report.error(f"素材哈希不一致：{path}")


def check_output(report: Report, episode: Path, scene: dict | None) -> None:
    outputs = sorted((episode / "output").glob("*.mp4"))
    if not outputs:
        report.warn("尚未渲染成片（output/*.mp4）")
        return
    if scene is None:
        return
    fps = int(scene["episode"]["fps"])
    expected = int(scene["episode"]["durationInFrames"]) / fps
    for path in outputs:
        try:
            media = lib.probe_media(path)
        except Exception as exc:  # noqa: BLE001
            report.error(f"无法读取成片 {path.name}：{exc}")
            continue
        kinds = {stream.get("codec_type") for stream in media.get("streams", [])}
        if "video" not in kinds:
            report.error(f"成片 {path.name} 没有视频流")
        if "audio" not in kinds:
            report.error(f"成片 {path.name} 没有音频流")
        duration = float(media.get("format", {}).get("duration", 0))
        if abs(duration - expected) > 0.6:
            report.error(f"成片 {path.name} 时长 {duration:.2f}s 与预期 {expected:.2f}s 不符")


def validate_episode(spec: str) -> Report:
    episode = lib.resolve_episode(spec)
    report = Report(episode)
    config = lib.load_json(episode / "episode.yaml")
    validate_schema(report, "episode.yaml", config, "episode")

    characters = check_characters(report, config)
    script, board_shots = check_script_and_board(
        report,
        config,
        lib.load_json(episode / "script.json"),
        lib.load_json(episode / "storyboard.json"),
        characters,
    )
    validate_schema(
        report,
        "storyboard.json",
        lib.load_json(episode / "storyboard.json"),
        "storyboard",
    )

    scene_path = episode / "project" / "scene.json"
    scene = lib.load_json(scene_path) if scene_path.is_file() else None
    if scene is None:
        report.warn("尚未生成 project/scene.json，先运行 prepare.py")

    timing = check_timing(report, episode, config, script, scene) if script else None
    check_scene(report, episode, characters, script, scene, timing)
    check_lock(report, episode)
    check_output(report, episode, scene)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="校验剧集数据、时间轴、素材和成片")
    parser.add_argument("--episode", action="append", default=[], help="剧集 id 或路径，可重复")
    parser.add_argument("--all", action="store_true", help="校验 videos/ 下所有剧集")
    args = parser.parse_args()

    specs = args.episode or [path.name for path in lib.episode_dirs()]
    if not specs:
        print("没有可校验的剧集")
        return 1

    failed = 0
    for spec in specs:
        report = validate_episode(spec)
        print(f"=== {report.episode.name} ===")
        for warning in report.warnings:
            print(f"  WARN {warning}")
        for error in report.errors:
            print(f"  ERROR {error}")
        if report.ok:
            print("  PASS")
        else:
            failed += 1
            print(f"  FAIL（{len(report.errors)} 个错误）")
        print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
