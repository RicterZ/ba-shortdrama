"""Shared helpers for the BA short-drama production pipeline."""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ASSETS_ROOT_FILE = ROOT / ".ba-assets-root"


def _main_checkout() -> Path:
    """Primary checkout of this repository; ROOT itself unless ROOT is a git worktree."""
    dotgit = ROOT / ".git"
    if not dotgit.is_file():
        return ROOT
    text = dotgit.read_text(encoding="utf-8").strip()
    if not text.startswith("gitdir:"):
        return ROOT
    gitdir = Path(text.split(":", 1)[1].strip())
    if not gitdir.is_absolute():
        gitdir = ROOT / gitdir
    commondir = gitdir / "commondir"
    if not commondir.is_file():
        return ROOT
    common = Path(commondir.read_text(encoding="utf-8").strip())
    if not common.is_absolute():
        common = gitdir / common
    main = common.resolve().parent
    return main if main.is_dir() else ROOT


def _assets_root() -> Path:
    """Checkout that holds the shared asset library (`data/`, `local/`).

    Order: $BA_ASSETS_ROOT, then the untracked `.ba-assets-root` file at the
    repository root, then the primary checkout (found through git worktree
    metadata; the repository root itself when this is not a worktree).
    """
    raw = os.environ.get("BA_ASSETS_ROOT", "").strip()
    source = "BA_ASSETS_ROOT"
    if not raw and ASSETS_ROOT_FILE.is_file():
        raw = ASSETS_ROOT_FILE.read_text(encoding="utf-8").strip()
        source = str(ASSETS_ROOT_FILE)
    if not raw:
        return _main_checkout()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_dir():
        raise SystemExit(f"资源根不存在（来自 {source}）：{path}")
    return path


def _output_root() -> Path:
    """Checkout whose `videos/` holds episode output (script, audio, renders).

    Output is per episode but must live in one place outside git so that it
    survives branch switches and task worktrees. Order: $BA_OUTPUT_ROOT, then
    the asset root.
    """
    raw = os.environ.get("BA_OUTPUT_ROOT", "").strip()
    if not raw:
        return ASSETS
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_dir():
        raise SystemExit(f"产物根不存在（来自 BA_OUTPUT_ROOT）：{path}")
    return path


ASSETS = _assets_root()
OUTPUT = _output_root()
VIDEOS = OUTPUT / "videos"
CHARACTERS = ASSETS / "data" / "characters"
SCENES = ASSETS / "data" / "scenes"
SCHEMAS = ROOT / "code" / "ba-production" / "schemas"
LOCAL_ENV = ASSETS / "local" / ".env"

DEFAULT_TIMING = {
    "intro_frames": 60,
    "lead_in_frames": 18,
    "tail_frames": 14,
    "min_line_frames": 48,
    "shot_cut_lead_frames": 15,
    "shot_tail_frames": 18,
    "outro_frames": 24,
}

DEFAULT_SUBTITLE = {
    "max_chars_per_line": 26,
    "max_lines": 2,
}

# Transitions are rendered by @remotion/transitions. New episodes get this block
# by default; an episode without it never adds a transition (older episodes keep
# their hard cuts).
DEFAULT_TRANSITIONS = {
    "on": "scene-change",
    "type": "fade",
    "durationInFrames": 12,
}

TRANSITION_TYPES = ("fade", "slide", "wipe", "flip", "clock-wipe", "iris", "none")

TRANSITION_DIRECTIONS = {
    "slide": ("from-left", "from-top", "from-right", "from-bottom"),
    "wipe": (
        "from-left",
        "from-top-left",
        "from-top",
        "from-top-right",
        "from-right",
        "from-bottom-right",
        "from-bottom",
        "from-bottom-left",
    ),
    "flip": ("from-left", "from-right", "from-top", "from-bottom"),
}

TRANSITION_EASINGS = ("linear", "ease-in-out")

VIDEO_EXTS = {".mp4", ".webm", ".mov"}


def load_json(path: Path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def episode_dirs() -> list[Path]:
    if not VIDEOS.is_dir():
        return []
    return sorted(p for p in VIDEOS.iterdir() if p.is_dir() and not p.name.startswith("."))


_EPISODE_LOCKS: list = []


def lock_episode(episode: Path) -> None:
    """Hold an exclusive lock on the episode until this process exits."""
    import fcntl

    handle = (episode / ".lock").open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.seek(0)
        holder = handle.read().strip() or "未知进程"
        handle.close()
        raise SystemExit(f"剧集 {episode.name} 正被另一个任务写入（{holder}），等它结束再试")
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid {os.getpid()} @ {ROOT}\n")
    handle.flush()
    _EPISODE_LOCKS.append(handle)


def resolve_episode(spec: str, lock: bool = False) -> Path:
    """Accept an episode id, a path relative to the output root, or an absolute path."""
    candidate = Path(spec).expanduser()
    if candidate.is_absolute():
        path = candidate
    elif "/" in spec:
        path = (OUTPUT / candidate).resolve()
    else:
        path = VIDEOS / spec
    if not path.is_dir():
        raise SystemExit(f"找不到剧集目录：{path}")
    path = path.resolve()
    if lock:
        lock_episode(path)
    return path


def read_character(character_id: str) -> dict:
    """Load a character profile: persona, voice provider binding and outfit sprites."""
    cdir = CHARACTERS / character_id
    profile_path = cdir / "profile.yaml"
    if not profile_path.is_file():
        raise FileNotFoundError(f"缺少角色 profile：{profile_path}")

    profile = load_json(profile_path)
    outfits: dict[str, dict] = {}
    for outfit_id, outfit in (profile.get("outfits") or {}).items():
        sprites = {}
        for expression, meta in (outfit.get("sprites") or {}).items():
            sprites[expression] = {
                "path": cdir / meta["path"],
                "sha256": meta.get("sha256"),
            }
        if "default" not in sprites:
            raise ValueError(f"角色 {character_id} 的服装 {outfit_id} 没有 default 立绘")
        outfits[outfit_id] = {
            "id": outfit_id,
            "name": outfit.get("name", outfit_id),
            "sprites": sprites,
        }
    if not outfits:
        raise ValueError(f"角色 {character_id} 没有配置任何服装")
    default_outfit = profile.get("default_outfit") or next(iter(outfits))
    if default_outfit not in outfits:
        raise ValueError(f"角色 {character_id} 的 default_outfit {default_outfit!r} 不存在")

    return {
        "id": character_id,
        "dir": cdir,
        "profile": profile,
        "outfits": outfits,
        "default_outfit": default_outfit,
        "voice": profile.get("voice", {}),
    }


def read_scene(scene_id: str, variant: str | None = None) -> dict:
    """Load a scene profile and resolve one lighting variant into a flat palette.

    Background art is always supplied from outside: a profile may point at one
    image (`image`) and a variant may override it. The returned `image_source` is
    an absolute working path for prepare.py to copy; it never goes into scene.json.
    """
    path = SCENES / scene_id / "scene.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"缺少场景 profile：{path}")
    data = load_json(path)
    variants = data.get("variants") or {}
    variant_id = variant or data.get("default_variant") or "default"
    if variants and variant_id not in variants:
        raise ValueError(
            f"场景 {scene_id} 没有变体 {variant_id!r}，可选：{', '.join(sorted(variants))}"
        )
    variant_data = variants.get(variant_id, {})
    resolved = {**(data.get("palette") or {}), **variant_data}
    resolved.pop("label", None)
    resolved.pop("image", None)
    lighting = resolved.pop("lighting", "day")
    image_ref = variant_data.get("image") or data.get("image")
    image_path = SCENES / scene_id / image_ref if image_ref else None
    return {
        "id": data["id"],
        "name": data.get("name", data["id"]),
        "renderer": data["renderer"],
        "variant": variant_id,
        "lighting": lighting,
        "palette": resolved,
        "image": None,
        "image_source": str(image_path) if image_path else "",
        "image_ref": image_ref or "",
    }


def load_local_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if LOCAL_ENV.is_file():
        for line in LOCAL_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def env_value(name: str) -> str:
    return os.environ.get(name) or load_local_env().get(name, "")


def text_units(text: str) -> float:
    """Approximate rendered width in CJK character units."""
    total = 0.0
    for ch in text:
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF or 0x3000 <= code <= 0x303F or 0xFF00 <= code <= 0xFFEF:
            total += 1.0
        elif ch.isspace():
            total += 0.35
        elif ch.isascii():
            total += 0.56
        else:
            total += 0.85
    return total


def wrapped_lines(text: str, max_chars: int) -> int:
    units = text_units(text)
    return max(1, math.ceil(units / max_chars))


def transition_defaults(spec, config: dict | None) -> dict:
    """Defaults an episode's `transitions` block applies to one shot's spec.

    A shot that names its own type only inherits the episode duration; a
    `direction` written for another presentation would not validate.
    """
    config = dict(config) if isinstance(config, dict) else {}
    if not isinstance(spec, (str, dict)):
        return config
    explicit_type = spec if isinstance(spec, str) else spec.get("type")
    if explicit_type:
        duration = config.get("durationInFrames")
        return {"durationInFrames": duration} if duration is not None else {}
    return config


def parse_transition(spec, defaults: dict | None = None) -> dict | None:
    """Normalize a storyboard/episode transition spec into a flat dict.

    Returns None for a hard cut (`type: "none"`). Episode-level defaults fill in
    any field the spec leaves out. Raises ValueError for anything the template
    cannot render.
    """
    defaults = defaults or {}
    if isinstance(spec, str):
        data: dict = {"type": spec}
    elif isinstance(spec, dict):
        data = dict(spec)
    else:
        raise ValueError(f"transition 必须是字符串或对象，收到 {type(spec).__name__}")

    kind = data.get("type") or defaults.get("type") or DEFAULT_TRANSITIONS["type"]
    if kind not in TRANSITION_TYPES:
        raise ValueError(f"未知转场类型 {kind!r}，可选：{', '.join(TRANSITION_TYPES)}")
    if kind == "none":
        return None

    merged = {**defaults, **data}
    duration = merged.get("durationInFrames", DEFAULT_TRANSITIONS["durationInFrames"])
    if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
        raise ValueError("transition.durationInFrames 必须是正整数")

    parsed = {"type": kind, "durationInFrames": duration}

    direction = merged.get("direction")
    if direction is not None:
        allowed = TRANSITION_DIRECTIONS.get(kind)
        if allowed is None:
            raise ValueError(f"转场 {kind} 不支持 direction")
        if direction not in allowed:
            raise ValueError(f"转场 {kind} 的 direction 不支持 {direction!r}，可选：{', '.join(allowed)}")
        parsed["direction"] = direction

    easing = merged.get("easing")
    if easing is not None:
        if easing not in TRANSITION_EASINGS:
            raise ValueError(f"转场 easing 不支持 {easing!r}，可选：{', '.join(TRANSITION_EASINGS)}")
        parsed["easing"] = easing

    perspective = merged.get("perspective")
    if perspective is not None:
        if kind != "flip":
            raise ValueError("转场 perspective 只用于 flip")
        parsed["perspective"] = float(perspective)

    fade_out = merged.get("shouldFadeOutExitingScene")
    if fade_out is not None:
        if kind != "fade":
            raise ValueError("转场 shouldFadeOutExitingScene 只用于 fade")
        parsed["shouldFadeOutExitingScene"] = bool(fade_out)

    return parsed


def line_id(entry: dict, index: int) -> str:
    return entry.get("id") or f"L{index + 1}"


def normalize_script(script: list[dict]) -> list[dict]:
    normalized = []
    seen = set()
    for index, entry in enumerate(script):
        if not isinstance(entry, dict):
            raise ValueError(f"script.json 第 {index + 1} 项不是对象")
        lid = line_id(entry, index)
        if lid in seen:
            raise ValueError(f"script.json 中台词 id 重复：{lid}")
        seen.add(lid)
        text = (entry.get("text") or "").strip()
        if not text:
            raise ValueError(f"台词 {lid} 为空")
        line = {
            "id": lid,
            "speaker": entry.get("speaker") or "",
            "emotion": entry.get("emotion") or "default",
            "text": text,
        }
        # 可选：实际送去合成的台词。text 仍是屏幕字幕，voice_text 用于外语配音。
        spoken = (entry.get("voice_text") or "").strip()
        if spoken:
            line["voice_text"] = spoken
        normalized.append(line)
    return normalized


def spoken_text(line: dict) -> str:
    """Text sent to TTS: voice_text when present, otherwise the subtitle text."""
    return (line.get("voice_text") or line.get("text") or "").strip()


def probe_duration(path: Path) -> float:
    import subprocess

    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    )
    return float(out.strip())


def probe_media(path: Path) -> dict:
    import subprocess

    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        text=True,
    )
    return json.loads(out)


def voice_rate(value: float) -> str:
    return f"{round((float(value) - 1.0) * 100):+d}%"


def safe_slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-") or "item"
