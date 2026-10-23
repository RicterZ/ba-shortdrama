#!/usr/bin/env python3
"""Regression tests for fetch_sprites: neutral-sprite mapping and fail-closed fetching.

Covers the two review findings:

1. `default` must use the explicit per-outfit key (battle -> 02, maid ->
   diorama_00), not whichever key `setdefault` happened to see first.
2. A missing upstream URL or a missing/corrupted local file must abort before
   rewriting `sprites/manifest.json` or `profile.yaml`, leaving the previous
   index (including a non-empty `missing`) untouched.

No network access: wiki/API/download calls are replaced with fixtures.

Example:
    ../carocut/.venv/bin/python scripts/test_fetch_sprites.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fetch_sprites as fs  # noqa: E402
import lib  # noqa: E402

WORK = lib.ROOT / "local" / "tmp" / "test-fetch-sprites"

PAGE = """
== Standard ==
{{Sprite
|Id=Test
|Type=spr
|CharacterName=Test
|CharacterVariant=
|Background=
}}
<gallery>
Test_00.png
Test_01.png
</gallery>
"""


def make_png(path: Path, color=(190, 100, 150, 255)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (4, 4), color).save(path)


def make_entry(character_dir: Path, outfit: str, key: str) -> dict:
    relative = Path("sprites") / outfit / f"{key}.png"
    path = character_dir / relative
    make_png(path)
    return {
        "key": key,
        "file": str(path.relative_to(lib.ROOT)),
        "size": path.stat().st_size,
        "sha256": fs.sha256_file(path),
    }


def write_profile(character_dir: Path, *, outfit: str = "battle") -> Path:
    path = character_dir / "profile.yaml"
    lib.write_json(
        path,
        {
            "schema_version": 2,
            "id": character_dir.name,
            "name": "测试角色",
            "voice": {"provider": "test"},
            "default_outfit": outfit,
            "outfits": {},
            "missing": ["keep-me"],
        },
    )
    return path


def test_default_mapping() -> list[str]:
    failures: list[str] = []
    character_dir = WORK / "characters" / "defaults"
    shutil.rmtree(character_dir, ignore_errors=True)
    write_profile(character_dir)

    specs = {
        "default": ["00", "01"],
        "maid": ["diorama_00", "diorama_10", "diorama_99"],
        "battle": ["00", "02", "99"],
        "winter": ["00", "05"],
    }
    manifest = {"character": {"outfits": []}}
    for outfit, keys in specs.items():
        manifest["character"]["outfits"].append(
            {
                "id": outfit,
                "name": outfit,
                "expected": len(keys),
                "sprites": [make_entry(character_dir, outfit, key) for key in keys],
            }
        )

    fs.update_profile_outfits(character_dir, manifest)
    profile = lib.load_json(character_dir / "profile.yaml")
    outfits = profile["outfits"]

    expectations = {
        "default": ("00", "00"),
        "maid": ("diorama_00", "diorama_00"),
        "battle": ("02", "02"),
        "winter": ("00", "00"),
    }
    for outfit, (default_key, neutral_key) in expectations.items():
        sprites = outfits[outfit]["sprites"]
        default_path = sprites["default"]["path"]
        neutral_path = sprites["neutral"]["path"]
        if not default_path.endswith(f"{default_key}.png"):
            failures.append(f"{outfit} 的 default 指向 {default_path}，应为 {default_key}.png")
        if not neutral_path.endswith(f"{neutral_key}.png"):
            failures.append(f"{outfit} 的 neutral 指向 {neutral_path}，应为 {neutral_key}.png")
    if outfits["battle"]["sprites"]["default"]["path"] != outfits["battle"]["sprites"]["02"]["path"]:
        failures.append("battle 的 default 没有指向 02")
    if profile.get("missing") != []:
        failures.append(f"完整抓取后 missing 应为空，实际 {profile.get('missing')!r}")
    return failures


def test_missing_url_aborts_without_overwrite() -> list[str]:
    failures: list[str] = []
    character_dir = WORK / "characters" / "missing-url"
    shutil.rmtree(character_dir, ignore_errors=True)
    profile_path = write_profile(character_dir)
    manifest_path = character_dir / "sprites" / "manifest.json"
    lib.write_json(manifest_path, {"sentinel": "old-manifest"})
    profile_before = profile_path.read_text(encoding="utf-8")
    manifest_before = manifest_path.read_text(encoding="utf-8")

    original = (fs.CHARACTERS, fs.wikitext, fs.image_urls, fs.download)
    fs.CHARACTERS = WORK / "characters"
    fs.wikitext = lambda page: PAGE
    fs.image_urls = lambda files: {"Test_00.png": {"url": "https://example.invalid/Test_00.png"}}

    def unexpected_download(url: str, dest: Path) -> dict:
        raise AssertionError(f"缺 URL 时不应开始下载：{url}")

    fs.download = unexpected_download
    try:
        fs.fetch_character("Test", slug="missing-url")
    except SystemExit:
        pass
    except Exception as error:  # noqa: BLE001 - the test reports the actual failure
        failures.append(f"缺 URL 时应以 SystemExit 失败，实际抛出 {type(error).__name__}: {error}")
    else:
        failures.append("缺 URL 时脚本仍然成功结束")
    finally:
        fs.CHARACTERS, fs.wikitext, fs.image_urls, fs.download = original

    if manifest_path.read_text(encoding="utf-8") != manifest_before:
        failures.append("缺 URL 时 manifest 被覆盖")
    if profile_path.read_text(encoding="utf-8") != profile_before:
        failures.append("缺 URL 时 profile/missing 被覆盖")
    return failures


def test_missing_file_aborts_without_overwrite() -> list[str]:
    failures: list[str] = []
    character_dir = WORK / "characters" / "missing-file"
    shutil.rmtree(character_dir, ignore_errors=True)
    profile_path = write_profile(character_dir)
    profile_before = profile_path.read_text(encoding="utf-8")

    ghost = character_dir / "sprites" / "battle" / "02.png"
    manifest = {
        "character": {
            "outfits": [
                {
                    "id": "battle",
                    "name": "武装",
                    "expected": 1,
                    "sprites": [
                        {
                            "key": "02",
                            "file": str(ghost.relative_to(lib.ROOT)),
                            "sha256": "0" * 64,
                        }
                    ],
                }
            ]
        }
    }
    try:
        fs.update_profile_outfits(character_dir, manifest)
    except SystemExit:
        pass
    except Exception as error:  # noqa: BLE001
        failures.append(f"缺文件时应以 SystemExit 失败，实际抛出 {type(error).__name__}: {error}")
    else:
        failures.append("缺文件时 profile 仍然被写入")

    if profile_path.read_text(encoding="utf-8") != profile_before:
        failures.append("缺文件时 profile/missing 被覆盖")
    return failures


def test_count_mismatch_aborts_without_overwrite() -> list[str]:
    failures: list[str] = []
    character_dir = WORK / "characters" / "count-mismatch"
    shutil.rmtree(character_dir, ignore_errors=True)
    profile_path = write_profile(character_dir)
    profile_before = profile_path.read_text(encoding="utf-8")

    manifest = {
        "character": {
            "outfits": [
                {
                    "id": "battle",
                    "name": "武装",
                    "expected": 2,
                    "sprites": [make_entry(character_dir, "battle", "02")],
                }
            ]
        }
    }
    try:
        fs.update_profile_outfits(character_dir, manifest)
    except SystemExit:
        pass
    except Exception as error:  # noqa: BLE001
        failures.append(f"数量不符时应以 SystemExit 失败，实际抛出 {type(error).__name__}: {error}")
    else:
        failures.append("数量不符时 profile 仍然被写入")

    if profile_path.read_text(encoding="utf-8") != profile_before:
        failures.append("数量不符时 profile/missing 被覆盖")
    return failures


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)
    failures = []
    for test in (
        test_default_mapping,
        test_missing_url_aborts_without_overwrite,
        test_missing_file_aborts_without_overwrite,
        test_count_mismatch_aborts_without_overwrite,
    ):
        failures.extend(test())

    if failures:
        print("FAIL")
        for failure in failures:
            print(f"  - {failure}")
        print(f"测试工作目录保留在 {WORK}")
        return 1
    print("PASS 武装/女仆默认表情正确；缺 URL、缺文件、数量不符均失败且不覆盖索引")
    shutil.rmtree(WORK, ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(f"测试工作目录保留在 {WORK}")
        raise
