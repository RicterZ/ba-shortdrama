"""Shared helpers for the BA short-drama production pipeline."""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VIDEOS = ROOT / "videos"
CHARACTERS = ROOT / "data" / "characters"
SCENES = ROOT / "data" / "scenes"
SCHEMAS = ROOT / "code" / "ba-production" / "schemas"
LOCAL_ENV = ROOT / "local" / ".env"

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


def resolve_episode(spec: str) -> Path:
    """Accept an episode id, a relative path, or an absolute path."""
    candidate = Path(spec).expanduser()
    if candidate.is_absolute():
        path = candidate
    elif "/" in spec:
        path = (ROOT / candidate).resolve()
    else:
        path = VIDEOS / spec
    if not path.is_dir():
        raise SystemExit(f"找不到剧集目录：{path}")
    return path.resolve()


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
        normalized.append(
            {
                "id": lid,
                "speaker": entry.get("speaker") or "",
                "emotion": entry.get("emotion") or "default",
                "text": text,
            }
        )
    return normalized


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
