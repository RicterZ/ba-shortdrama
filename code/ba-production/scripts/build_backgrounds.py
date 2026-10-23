#!/usr/bin/env python3
"""Build the reusable background library from the owner's archive drop.

Reads every `temp/*.zip`, unpacks the images into a private staging directory
(without touching the archives), then crops each usable background to 16:9,
writes it to `data/scenes/<scene-id>/backgrounds/<scene-id>-<variant>.jpg` and
indexes everything in `data/backgrounds/manifest.json`.

The crop is always a centred 16:9 window and its exact box is recorded in the
manifest; images are never stretched or padded. Output is sRGB JPEG at quality
90, 1920x1080 when the source can supply it, otherwise 1280x720. Sources are
never upscaled except for a handful of off-size originals, which the manifest
flags as anomalies.

Examples:
    ../carocut/.venv/bin/python scripts/build_backgrounds.py
    ../carocut/.venv/bin/python scripts/build_backgrounds.py --inventory-only
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

SOURCE = lib.ROOT / "temp"
STAGING = lib.ROOT / "local" / "backgrounds-library" / "staging"
MANIFEST = lib.ROOT / "data" / "backgrounds" / "manifest.json"

JPEG_QUALITY = 90
HD = (1920, 1080)
SD = (1280, 720)

# Zip stem -> stable English category slug used by the manifest and scene index.
CATEGORIES = {
    "学校相关": "school",
    "城市街景": "city",
    "自然郊外": "nature",
    "通用外景": "outdoor",
    "剧情特殊": "story-special",
    "远景氛围": "distant-atmosphere",
    "交通基建": "transport",
    "商业设施": "commercial",
    "通用内景": "interior",
}

# Suffixes that describe a variant of the same location rather than a new place.
VARIANT_TOKENS = {
    "night", "night2", "night3", "night4",
    "sunset", "dawn", "day", "fineday",
    "rain", "rainy", "cloudy", "clowdy", "cloud", "fog", "snow",
    "blur", "blur2", "dark",
    "off", "off2", "on",
    "erode", "erode2", "ruin", "ruin2", "collapsed", "rebuild", "archive",
    "covered", "koinugo", "activated", "activated2", "empty", "empty2",
    "chaos", "fake", "safe", "open", "in", "tent",
    "v1", "v2", "v3", "v4", "v5", "v6",
} | {str(i) for i in range(1, 10)}

# Not backgrounds: overlays, logos and animation frames. They stay in the
# inventory so nothing is silently dropped, but never enter the library.
EXCLUSIONS = [
    (re.compile(r"^BG_Black_Effect\d+$"), "effect-overlay"),
    (re.compile(r"^BG_CS_Logo_"), "logo-ui"),
    (re.compile(r"^BG_Bar_(Night_)?1_\d+$"), "animation-frame"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 temp/*.zip 构建背景素材库和 manifest")
    parser.add_argument("--source", default=str(SOURCE), help="原始 zip 所在目录")
    parser.add_argument("--staging", default=str(STAGING), help="解包暂存目录")
    parser.add_argument("--manifest", default=str(MANIFEST), help="输出 manifest 路径")
    parser.add_argument("--scenes", default=str(lib.SCENES), help="交付图根目录，默认 data/scenes")
    parser.add_argument("--inventory-only", action="store_true", help="只盘点，不裁切、不写交付图")
    return parser.parse_args()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def decode_image(path: Path) -> tuple[int, int]:
    """Fully decode the file, not just read its header.

    `Image.open` only parses the header; a truncated or corrupt file can still
    report a plausible size. `load()` forces the decoder to read every pixel so
    damaged files are caught here instead of failing later in the crop step.
    """
    with Image.open(path) as image:
        image.load()
        return image.size


def unpack(source: Path, staging: Path) -> tuple[dict[str, list[Path]], list[dict]]:
    """Extract each archive into its own directory.

    Returns `(files grouped by zip, extraction failures)`. A broken archive or
    entry is recorded and skipped so one bad file cannot abort the inventory.
    """
    grouped: dict[str, list[Path]] = {}
    damaged: list[dict] = []
    for archive in sorted(source.glob("*.zip")):
        category = CATEGORIES.get(archive.stem)
        if category is None:
            print(f"跳过未知分类的压缩包：{archive.name}")
            continue
        out_dir = staging / archive.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        files: list[Path] = []
        try:
            zf = zipfile.ZipFile(archive)
        except Exception as exc:  # noqa: BLE001
            damaged.append(
                {
                    "source_zip": archive.name,
                    "source_file": "",
                    "source_bytes": archive.stat().st_size,
                    "source_sha256": sha256_file(archive),
                    "stage": "archive",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        with zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename).name
                if not name or name.startswith("._") or name == ".DS_Store":
                    continue
                if "__MACOSX" in info.filename:
                    continue
                target = out_dir / name
                if not target.is_file():
                    try:
                        with zf.open(info) as src, target.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
                    except Exception as exc:  # noqa: BLE001
                        target.unlink(missing_ok=True)
                        damaged.append(
                            {
                                "source_zip": archive.name,
                                "source_file": name,
                                "source_bytes": info.file_size,
                                "source_sha256": "",
                                "stage": "extract",
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                        continue
                files.append(target)
        grouped[archive.name] = files
    return grouped, damaged


def split_name(stem: str) -> tuple[str, str]:
    """Split a source filename into (location stem, variant suffix)."""
    value = stem
    for prefix in ("BG_", "Event_"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    parts = value.split("_")
    suffix: list[str] = []
    while parts and parts[-1].lower() in VARIANT_TOKENS:
        suffix.insert(0, parts.pop().lower())
    # Never collapse a whole name away (e.g. a hypothetical `BG_Night.jpg`).
    if not parts:
        return value, ""
    return "_".join(parts), "-".join(suffix)


def scene_id_from(stem: str) -> str:
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", stem)
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return value.lower()


def display_name(stem: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", stem)
    return spaced.replace("_", " ").strip()


def lighting_for(variant: str) -> str:
    head = variant.split("-")[0]
    if head.startswith("night") or head == "dark":
        return "night"
    if head == "sunset":
        return "sunset"
    if head == "dawn":
        return "dawn"
    return "day"


def tags_for(scene_id: str, category: str, variant: str) -> list[str]:
    parts = [part for part in scene_id.split("-") if not part.isdigit()]
    tags = [part.lower() for part in parts]
    tags += [category, variant, lighting_for(variant)]
    seen: list[str] = []
    for tag in tags:
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def target_size(source_width: int) -> tuple[int, int]:
    return HD if source_width >= HD[0] else SD


def crop_box(width: int, height: int) -> tuple[int, int, int, int]:
    """Largest centred 16:9 box that fits the source."""
    if width * 9 >= height * 16:
        box_w, box_h = width, round(width * 9 / 16)
        if box_h > height:
            box_h = height
            box_w = round(height * 16 / 9)
    else:
        box_h, box_w = height, round(height * 16 / 9)
        if box_w > width:
            box_w = width
            box_h = round(width * 9 / 16)
    box_w = min(box_w, width)
    box_h = min(box_h, height)
    x = (width - box_w) // 2
    y = (height - box_h) // 2
    return x, y, box_w, box_h


def save_background(source: Path, target: Path, size: tuple[int, int]):
    with Image.open(source) as image:
        image = image.convert("RGB")
        width, height = image.size
        x, y, box_w, box_h = crop_box(width, height)
        cropped = image.crop((x, y, x + box_w, y + box_h))
        resized = cropped.resize(size, Image.Resampling.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True)
        resized.save(target, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return (x, y, box_w, box_h)


def manifest_path_for(target: Path) -> str:
    try:
        return str(target.resolve().relative_to(lib.ROOT))
    except ValueError:
        return str(target.resolve())


def main() -> int:
    args = parse_args()
    source = Path(args.source).resolve()
    staging = Path(args.staging).resolve()
    manifest_path = Path(args.manifest).resolve()
    scenes_root = Path(args.scenes).resolve()
    if not source.is_dir():
        raise SystemExit(f"找不到原始压缩包目录：{source}")

    grouped, damaged = unpack(source, staging)
    entries: list[dict] = []
    excluded: list[dict] = []
    anomalies: list[dict] = []
    seen_hashes: dict[str, dict] = {}
    duplicates: list[dict] = []

    for zip_name, files in grouped.items():
        category = CATEGORIES[Path(zip_name).stem]
        for path in files:
            raw = path.read_bytes()
            source_sha = sha256_bytes(raw)
            source_record = {
                "source_zip": zip_name,
                "source_file": path.name,
                "source_bytes": len(raw),
                "source_sha256": source_sha,
            }
            try:
                width, height = decode_image(path)
            except Exception as exc:  # noqa: BLE001
                damaged.append(
                    {
                        **source_record,
                        "stage": "decode",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue

            kind = next((reason for pattern, reason in EXCLUSIONS if pattern.match(path.stem)), None)
            if kind:
                excluded.append(
                    {
                        **source_record,
                        "reason": kind,
                        "width": width,
                        "height": height,
                    }
                )
                continue

            base, variant_suffix = split_name(path.stem)
            scene_id = scene_id_from(base)
            variant = variant_suffix or "default"
            entry_id = f"{scene_id}-{variant}"
            if source_sha in seen_hashes:
                duplicates.append(
                    {
                        "sha256": source_sha,
                        "first": seen_hashes[source_sha],
                        "duplicate": source_record,
                    }
                )
                continue
            seen_hashes[source_sha] = source_record

            out_size = target_size(width)
            target = scenes_root / scene_id / "backgrounds" / f"{entry_id}.jpg"
            if args.inventory_only:
                crop = crop_box(width, height)
                out_sha = ""
                out_bytes = 0
            else:
                try:
                    crop = save_background(path, target, out_size)
                    out_sha = sha256_file(target)
                    out_bytes = target.stat().st_size
                except Exception as exc:  # noqa: BLE001
                    damaged.append(
                        {
                            **source_record,
                            "stage": "encode",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    target.unlink(missing_ok=True)
                    continue

            canonical_sizes = {(1280, 900), (1600, 1124), (3160, 2220), (2048, 1439)}
            if (width, height) not in canonical_sizes:
                anomalies.append(
                    {
                        "id": entry_id,
                        "source_file": path.name,
                        "source_size": [width, height],
                        "issue": "off-size original",
                    }
                )
            if width < out_size[0]:
                anomalies.append(
                    {
                        "id": entry_id,
                        "source_file": path.name,
                        "source_size": [width, height],
                        "issue": f"source narrower than {out_size[0]}px; resampled up",
                    }
                )

            entry = {
                "id": entry_id,
                "scene_id": scene_id,
                "name": display_name(base),
                "category": category,
                "category_zh": Path(zip_name).stem,
                "variant": variant,
                "lighting": lighting_for(variant),
                "source_zip": zip_name,
                "source_file": path.name,
                "source_width": width,
                "source_height": height,
                "source_sha256": source_sha,
                "source_bytes": len(raw),
                "path": manifest_path_for(target),
                "width": out_size[0],
                "height": out_size[1],
                "crop": {"mode": "center", "box": list(crop)},
                "sha256": out_sha,
                "bytes": out_bytes,
                "quality": JPEG_QUALITY,
                "tags": tags_for(scene_id, category, variant),
            }
            entries.append(entry)

    entries.sort(key=lambda item: (item["scene_id"], item["variant"]))
    excluded.sort(key=lambda item: (item["source_zip"], item["source_file"]))
    damaged.sort(key=lambda item: (item["source_zip"], item["source_file"], item["stage"]))

    category_counts: dict[str, int] = {}
    scene_ids: set[str] = set()
    for entry in entries:
        category_counts[entry["category"]] = category_counts.get(entry["category"], 0) + 1
        scene_ids.add(entry["scene_id"])
    reason_counts: dict[str, int] = {}
    for item in excluded:
        reason_counts[item["reason"]] = reason_counts.get(item["reason"], 0) + 1
    damaged_counts: dict[str, int] = {}
    for item in damaged:
        damaged_counts[item["stage"]] = damaged_counts.get(item["stage"], 0) + 1
    extraction_failures = sum(1 for item in damaged if item["stage"] in ("archive", "extract"))

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_root": manifest_path_for(source),
        "target": {
            "aspect": "16:9",
            "width": SD[0],
            "height": SD[1],
            "hd_width": HD[0],
            "hd_height": HD[1],
            "format": "jpeg",
            "quality": JPEG_QUALITY,
            "color_space": "sRGB",
            "crop": "centre 16:9, recorded per entry; never stretch or pad",
        },
        "stats": {
            "source_files": sum(len(files) for files in grouped.values()) + extraction_failures,
            "library_entries": len(entries),
            "scenes": len(scene_ids),
            "excluded": len(excluded),
            "duplicate_sha256": len(duplicates),
            "damaged": len(damaged),
            "by_category": dict(sorted(category_counts.items())),
            "excluded_by_reason": dict(sorted(reason_counts.items())),
            "damaged_by_stage": dict(sorted(damaged_counts.items())),
        },
        "anomalies": anomalies,
        "duplicates": duplicates,
        "damaged": damaged,
        "entries": entries,
        "excluded": excluded,
    }
    lib.write_json(manifest_path, manifest)

    stats = manifest["stats"]
    print(
        f"背景库：{stats['library_entries']} 张 / {stats['scenes']} 个场景"
        f"（原始 {stats['source_files']}，排除 {stats['excluded']}，"
        f"重复 {stats['duplicate_sha256']}，损坏 {stats['damaged']}）"
    )
    print(f"manifest：{manifest_path}")
    if not args.inventory_only:
        print(f"交付目录：{scenes_root}/<scene-id>/backgrounds/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
