#!/usr/bin/env python3
"""Regression test for the background builder's inventory edge cases.

Builds a throwaway archive containing a valid background, its duplicate, an
excluded effect overlay, a garbage file and a truncated JPEG, then runs
`build_backgrounds.py` against it. The builder must finish with exit code 0,
keep the valid entries, and record the duplicate / excluded / damaged files
with their source archive, file name and byte size.

Example:
    uv run python scripts/test_backgrounds.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUILD = HERE / "build_backgrounds.py"
WORK = ROOT / "local" / "backgrounds-library" / "test-tmp"


def make_jpeg(path: Path, color: str, size: tuple[int, int] = (320, 240)) -> None:
    Image.new("RGB", size, color).save(path, "JPEG", quality=90)


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)
    source = WORK / "source"
    fixtures = WORK / "fixtures"
    staging = WORK / "staging"
    scenes = WORK / "scenes"
    manifest_path = WORK / "manifest.json"
    fixtures.mkdir(parents=True)

    make_jpeg(fixtures / "BG_TestRoom.jpg", "#88ccff")
    shutil.copy2(fixtures / "BG_TestRoom.jpg", fixtures / "BG_TestRoomCopy.jpg")
    make_jpeg(fixtures / "BG_TestRoom_Night.jpg", "#203050")
    make_jpeg(fixtures / "BG_Black_Effect1.jpg", "#000000")
    garbage = b"this is not an image\n"
    (fixtures / "BG_Broken.jpg").write_bytes(garbage)
    make_jpeg(fixtures / "BG_Truncated.jpg", "#ff8844", (640, 480))
    data = (fixtures / "BG_Truncated.jpg").read_bytes()
    (fixtures / "BG_Truncated.jpg").write_bytes(data[: len(data) // 2])
    truncated_bytes = (fixtures / "BG_Truncated.jpg").stat().st_size

    source.mkdir()
    with zipfile.ZipFile(source / "学校相关.zip", "w") as archive:
        for path in sorted(fixtures.iterdir()):
            archive.write(path, path.name)

    result = subprocess.run(
        [
            sys.executable,
            str(BUILD),
            "--source", str(source),
            "--staging", str(staging),
            "--manifest", str(manifest_path),
            "--scenes", str(scenes),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("FAIL 构建脚本没有正常结束")
        print(result.stdout)
        print(result.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    entries = manifest["entries"]
    expect(
        {entry["id"] for entry in entries} == {"test-room-default", "test-room-night"},
        f"入库条目不符合预期：{[entry['id'] for entry in entries]}",
    )
    for entry in entries:
        output = ROOT / entry["path"]
        expect(output.is_file(), f"输出图不存在：{entry['path']}")
        expect(entry["source_bytes"] > 0, f"{entry['id']} 缺少 source_bytes")

    excluded = manifest["excluded"]
    expect(len(excluded) == 1, f"排除项应为 1，实际 {len(excluded)}")
    if excluded:
        item = excluded[0]
        expect(item["source_file"] == "BG_Black_Effect1.jpg", "排除项文件名错误")
        expect(item["source_bytes"] > 0, "排除项缺少 source_bytes")
        expect(bool(item["source_sha256"]), "排除项缺少 source_sha256")
        expect(item["reason"] == "effect-overlay", "排除原因错误")

    damaged = manifest["damaged"]
    expect(len(damaged) == 2, f"损坏项应为 2，实际 {len(damaged)}")
    damaged_by_name = {item["source_file"]: item for item in damaged}
    expect("BG_Broken.jpg" in damaged_by_name, "未记录非图片文件 BG_Broken.jpg")
    expect("BG_Truncated.jpg" in damaged_by_name, "未记录截断文件 BG_Truncated.jpg")
    for name, item in damaged_by_name.items():
        expect(item["stage"] == "decode", f"{name} 的失败阶段应为 decode")
        expect(item["source_zip"] == "学校相关.zip", f"{name} 缺少来源压缩包")
        expect(item["source_bytes"] > 0, f"{name} 缺少 source_bytes")
        expect(bool(item["error"]), f"{name} 缺少错误信息")
    expect(
        damaged_by_name.get("BG_Truncated.jpg", {}).get("source_bytes") == truncated_bytes,
        "截断文件的 source_bytes 与实际不一致",
    )

    duplicates = manifest["duplicates"]
    expect(len(duplicates) == 1, f"重复项应为 1，实际 {len(duplicates)}")
    if duplicates:
        pair = {duplicates[0]["first"]["source_file"], duplicates[0]["duplicate"]["source_file"]}
        expect(pair == {"BG_TestRoom.jpg", "BG_TestRoomCopy.jpg"}, f"重复项记录有误：{pair}")
        expect(duplicates[0]["first"]["source_bytes"] > 0, "重复项 first 缺少 source_bytes")
        expect(duplicates[0]["duplicate"]["source_bytes"] > 0, "重复项 duplicate 缺少 source_bytes")

    expect(manifest["stats"]["library_entries"] == 2, "stats.library_entries 不正确")
    expect(manifest["stats"]["damaged"] == 2, "stats.damaged 不正确")
    expect(manifest["stats"]["duplicate_sha256"] == 1, "stats.duplicate_sha256 不正确")

    if failures:
        print("FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS 坏图/重复/排除项均被记录，构建继续完成")
    shutil.rmtree(WORK, ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(f"测试工作目录保留在 {WORK}")
        raise
