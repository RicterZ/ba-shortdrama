"""Read Spine 4.2 export bounds for a matching, uncropped standing PNG."""
import hashlib
import json
import math
import struct
from pathlib import Path
from PIL import Image

# Spine 4.2: 8-byte hash, length-prefixed version string, four BE floats.
SPINE_HEADER = b"\x074.2.33"
ASPECT_TOLERANCE = 0.02


def spine_bounds(skeleton: Path) -> tuple[float, float, float, float]:
    raw = skeleton.read_bytes()
    if len(raw) < 31 or raw[8:15] != SPINE_HEADER:
        raise ValueError("Only verified Spine 4.2.33 export headers are supported")
    x, y, width, height = struct.unpack_from(">ffff", raw, 15)
    if not all(math.isfinite(v) for v in (x, y, width, height)) or min(width, height) <= 0:
        raise ValueError("Invalid Spine bounds")
    return x, y, width, height


def aspect_error(image_size: tuple[int, int], bounds: tuple[float, float]) -> float:
    iw, ih = image_size
    width, height = bounds
    return abs((iw / ih) / (width / height) - 1)


def outfit_reference_sprites(directory: Path) -> list[tuple[str, Path]]:
    """Neutral standing PNG for each outfit, used only to compare aspect ratios."""
    found: list[tuple[str, Path]] = []
    profile_path = directory / "profile.yaml"
    if profile_path.is_file():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        for outfit_id, outfit in (profile.get("outfits") or {}).items():
            sprites = outfit.get("sprites") or {}
            entry = sprites.get("default") or sprites.get("00")
            if not isinstance(entry, dict) or not entry.get("path"):
                continue
            path = directory / entry["path"]
            if path.is_file():
                found.append((str(outfit_id), path))
    if found:
        return found
    sprites_root = directory / "sprites"
    if sprites_root.is_dir():
        for path in sorted(sprites_root.glob("*/00.png")):
            found.append((path.parent.name, path))
    return found


def spine_match_lines(directory: Path) -> list[str]:
    """Report which downloaded skel files are close in aspect to each outfit.

    A close aspect ratio is not identity. Callers must not write ``outfits.spine``
    from this report alone.
    """
    skels = sorted((directory / "kivo" / "spine").glob("*/*.skel"))
    if not skels:
        return []
    sprites = outfit_reference_sprites(directory)
    if not sprites:
        return [
            "还没有服装立绘，无法对照 skel。先拉取立绘，再人工确认后写入 profile 的 outfits.spine。"
        ]
    lines = [
        "立绘与 skel 宽高比对照（差超过 2% 视为不符；接近也不能代替人工确认，不会自动写入 outfits.spine）："
    ]
    for outfit_id, sprite in sprites:
        with Image.open(sprite) as image:
            size = image.size
        lines.append(f"  {outfit_id}  {sprite.relative_to(directory).as_posix()}")
        for skel in skels:
            relative = skel.relative_to(directory).as_posix()
            try:
                _, _, width, height = spine_bounds(skel)
            except ValueError as exc:
                lines.append(f"    无法读取 {relative}：{exc}")
                continue
            error = aspect_error(size, (width, height))
            label = "接近" if error <= ASPECT_TOLERANCE else "不符"
            lines.append(f"    {label} {relative}（差 {error:.1%}）")
    return lines


def read_coordinates(skeleton: Path, sprite: Path) -> dict:
    raw = skeleton.read_bytes()
    x, y, width, height = spine_bounds(skeleton)
    with Image.open(sprite) as image:
        iw, ih = image.size
    if aspect_error((iw, ih), (width, height)) > ASPECT_TOLERANCE:
        raise ValueError("PNG and Spine bounds differ: use the matching uncropped standing export")
    result = {"x": x, "y": y, "width": width, "height": height,
            "imageWidth": iw, "imageHeight": ih,
            "source": skeleton.name, "sha256": hashlib.sha256(raw).hexdigest()}
    calibrations = json.loads((Path(__file__).resolve().parents[1] / "templates" / "bubble-calibrations.json").read_text())
    if result["sha256"] in calibrations:
        result["bubbleAnchors"] = calibrations[result["sha256"]]["anchors"]
    return result
