#!/usr/bin/env python3
"""Check the background library, its manifest and the scene profiles that use it.

Verifies that `data/backgrounds/manifest.json` parses and is internally
consistent, that every listed image exists with the recorded size and SHA-256,
that no image is registered twice, and that every `data/scenes/<id>/scene.yaml`
passes `schemas/scene.json` and only points at registered backgrounds.

Examples:
    uv run python scripts/check_backgrounds.py
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import jsonschema
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

MANIFEST = lib.ASSETS / "data" / "backgrounds" / "manifest.json"
REQUIRED = (
    "id", "scene_id", "name", "category", "variant", "lighting",
    "source_zip", "source_file", "path", "width", "height", "crop", "sha256", "tags",
)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_manifest(report: Report, manifest: dict) -> dict[str, dict]:
    if manifest.get("schema_version") != 1:
        report.error("manifest.schema_version 必须是 1")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        report.error("manifest.entries 为空")
        return {}

    by_path: dict[str, dict] = {}
    by_sha: dict[str, str] = {}
    by_scene_variant: dict[tuple[str, str], str] = {}
    sizes = {(1280, 720), (1920, 1080)}

    for index, entry in enumerate(entries):
        label = entry.get("path") or f"entries[{index}]"
        if not isinstance(entry, dict):
            report.error(f"{label} 不是对象")
            continue
        missing = [key for key in REQUIRED if key not in entry]
        if missing:
            report.error(f"{label} 缺少字段：{', '.join(missing)}")
            continue

        scene_id = entry["scene_id"]
        variant = entry["variant"]
        expected = f"data/scenes/{scene_id}/backgrounds/{scene_id}-{variant}.jpg"
        if entry["path"] != expected:
            report.error(f"{label} 路径不符合命名规则，应为 {expected}")
        if entry["id"] != f"{scene_id}-{variant}":
            report.error(f"{label} 的 id 应为 {scene_id}-{variant}")

        key = (scene_id, variant)
        if key in by_scene_variant:
            report.error(f"场景 {scene_id} 的变体 {variant} 重复登记：{by_scene_variant[key]}")
        by_scene_variant[key] = entry["path"]

        if entry["path"] in by_path:
            report.error(f"manifest 路径重复：{entry['path']}")
        by_path[entry["path"]] = entry

        digest = entry["sha256"]
        if digest in by_sha:
            report.error(f"同一张图被登记为不同条目：{by_sha[digest]} 与 {entry['path']}")
        by_sha[digest] = entry["path"]

        image_path = lib.ASSETS / entry["path"]
        if not image_path.is_file():
            report.error(f"背景图不存在：{entry['path']}")
            continue
        actual = sha256(image_path)
        if actual != digest:
            report.error(f"哈希不一致：{entry['path']}（manifest {digest[:12]}…，实际 {actual[:12]}…）")

        with Image.open(image_path) as image:
            size = image.size
            if size != (entry["width"], entry["height"]):
                report.error(f"{entry['path']} 尺寸 {size} 与 manifest {(entry['width'], entry['height'])} 不一致")
            if image.format != "JPEG":
                report.error(f"{entry['path']} 不是 JPEG")
        if size not in sizes:
            report.error(f"{entry['path']} 输出尺寸 {size} 不在允许范围 {sorted(sizes)}")
        if abs(size[0] / size[1] - 16 / 9) > 0.01:
            report.error(f"{entry['path']} 输出不是 16:9：{size}")

        crop = entry["crop"]
        box = crop.get("box") if isinstance(crop, dict) else None
        if not isinstance(box, list) or len(box) != 4:
            report.error(f"{entry['path']} 的 crop.box 必须是 [x, y, w, h]")
            continue
        x, y, width, height = box
        if min(box) < 0 or width <= 0 or height <= 0:
            report.error(f"{entry['path']} 的裁切框非法：{box}")
        elif x + width > entry["source_width"] or y + height > entry["source_height"]:
            report.error(f"{entry['path']} 的裁切框超出原图：{box} vs 原图 {entry['source_width']}x{entry['source_height']}")
        elif abs(width / height - 16 / 9) > 0.01:
            report.error(f"{entry['path']} 的裁切框不是 16:9：{box}")
        expected_size = (1920, 1080) if width >= 1920 else (1280, 720)
        if size != expected_size:
            report.error(f"{entry['path']} 输出尺寸 {size} 与裁切宽度 {width} 不匹配，应为 {expected_size}")

        if abs(x - (entry["source_width"] - width) / 2) > 1:
            report.warn(f"{entry['path']} 的裁切不是居中（x={x}）")

    for item in manifest.get("excluded") or []:
        label = f"{item.get('source_zip')}/{item.get('source_file')}"
        if "path" in item:
            report.error(f"被排除的文件不应有交付路径：{label}")
        for key in ("source_zip", "source_file", "source_bytes", "source_sha256", "reason"):
            if key not in item:
                report.error(f"排除项 {label} 缺少字段：{key}")
        if not isinstance(item.get("source_bytes"), int) or item.get("source_bytes", 0) <= 0:
            report.error(f"排除项 {label} 的 source_bytes 缺失或非法")

    for item in manifest.get("damaged") or []:
        label = f"{item.get('source_zip')}/{item.get('source_file')}"
        if "path" in item:
            report.error(f"损坏文件不应有交付路径：{label}")
        for key in ("source_zip", "source_file", "source_bytes", "stage", "error"):
            if key not in item:
                report.error(f"损坏项 {label} 缺少字段：{key}")
        if not isinstance(item.get("source_bytes"), int):
            report.error(f"损坏项 {label} 的 source_bytes 缺失或非法")

    for item in manifest.get("duplicates") or []:
        for side in ("first", "duplicate"):
            source = item.get(side)
            if not isinstance(source, dict):
                report.error(f"重复项缺少 {side} 的来源记录")
                continue
            for key in ("source_zip", "source_file", "source_bytes"):
                if key not in source:
                    report.error(f"重复项的 {side} 缺少字段：{key}")

    entry_sources = {
        (entry.get("source_zip"), entry.get("source_file"))
        for entry in entries
        if isinstance(entry, dict)
    }
    for kind, items in (("排除", manifest.get("excluded") or []), ("损坏", manifest.get("damaged") or [])):
        for item in items:
            source = (item.get("source_zip"), item.get("source_file"))
            if source in entry_sources:
                report.error(f"{kind}项 {source[0]}/{source[1]} 同时被登记为入库背景")
    return by_path


def check_scene_profiles(report: Report, by_path: dict[str, dict]) -> int:
    schema = lib.load_json(lib.SCHEMAS / "scene.json")
    checked = 0
    owner: dict[str, str] = {}
    for scene_dir in sorted(lib.SCENES.iterdir()):
        if not scene_dir.is_dir() or scene_dir.name.startswith("."):
            continue
        profile_path = scene_dir / "scene.yaml"
        if not profile_path.is_file():
            continue
        checked += 1
        try:
            profile = lib.load_json(profile_path)
        except Exception as exc:  # noqa: BLE001
            report.error(f"{profile_path.relative_to(lib.ASSETS)} 无法解析：{exc}")
            continue
        try:
            jsonschema.validate(profile, schema)
        except jsonschema.ValidationError as exc:
            report.error(f"{profile_path.relative_to(lib.ASSETS)} 不符合 scene schema：{exc.message}")
            continue
        if profile.get("id") != scene_dir.name:
            report.error(f"{profile_path.relative_to(lib.ASSETS)} 的 id {profile.get('id')!r} 与目录名不一致")

        images: list[tuple[str, str]] = []
        if profile.get("image"):
            images.append(("image", profile["image"]))
        for variant_id, variant in (profile.get("variants") or {}).items():
            if isinstance(variant, dict) and variant.get("image"):
                images.append((f"variants.{variant_id}", variant["image"]))

        for where, relative in images:
            image_path = scene_dir / relative
            if not image_path.is_file():
                report.error(f"{profile_path.relative_to(lib.ASSETS)} 的 {where} 引用不存在的图片：{relative}")
                continue
            rel = str(image_path.resolve().relative_to(lib.ASSETS))
            entry = by_path.get(rel)
            if entry is None:
                report.error(f"{profile_path.relative_to(lib.ASSETS)} 的 {where} 图片没有登记在 manifest：{rel}")
                continue
            if entry["scene_id"] != scene_dir.name:
                report.error(f"{scene_dir.name} 引用了别的场景的图：{rel}（属于 {entry['scene_id']}）")
            if rel in owner and owner[rel] != scene_dir.name:
                report.error(f"同一张图被两个场景引用：{owner[rel]} 与 {scene_dir.name} → {rel}")
            owner[rel] = scene_dir.name

    # Every delivered background must be indexed.
    for image_path in sorted(lib.SCENES.glob("*/backgrounds/*")):
        if not image_path.is_file():
            continue
        rel = str(image_path.relative_to(lib.ASSETS))
        if rel not in by_path:
            report.error(f"交付目录里有未登记的背景图：{rel}")
    return checked


def check_sources(report: Report, manifest: dict) -> None:
    """Cross-check the source archive entries when temp/ is still around."""
    source_root = lib.ASSETS / manifest.get("source_root", "temp")
    if not source_root.is_dir():
        report.warn(f"原始压缩包目录不存在，跳过来源核对：{source_root}")
        return
    import zipfile

    names: dict[str, set[str]] = {}
    for entry in manifest["entries"]:
        zip_name = entry["source_zip"]
        if zip_name not in names:
            archive = source_root / zip_name
            if not archive.is_file():
                report.error(f"找不到来源压缩包：{zip_name}")
                names[zip_name] = set()
            else:
                with zipfile.ZipFile(archive) as zf:
                    names[zip_name] = {Path(item.filename).name for item in zf.infolist()}
        if entry["source_file"] not in names[zip_name]:
            report.error(f"{entry['source_file']} 不在 {zip_name} 中")


def main() -> int:
    parser = argparse.ArgumentParser(description="校验背景库 manifest 与场景 profile")
    parser.add_argument("--manifest", default=str(MANIFEST))
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    report = Report()
    if not manifest_path.is_file():
        print(f"FAIL 找不到 manifest：{manifest_path}")
        return 1
    try:
        manifest = lib.load_json(manifest_path)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL manifest 无法解析：{exc}")
        return 1

    by_path = check_manifest(report, manifest)
    scenes = check_scene_profiles(report, by_path) if by_path else 0
    check_sources(report, manifest)

    stats = manifest.get("stats") or {}
    print(
        f"背景库：{len(by_path)} 张 / {stats.get('scenes', '?')} 个场景；"
        f"scene profile：{scenes} 个；排除 {stats.get('excluded', '?')} 张；"
        f"损坏 {stats.get('damaged', len(manifest.get('damaged') or []))} 个"
    )
    for warning in report.warnings:
        print(f"  WARN {warning}")
    for error in report.errors:
        print(f"  ERROR {error}")
    print("PASS" if report.ok else f"FAIL（{len(report.errors)} 个错误）")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
