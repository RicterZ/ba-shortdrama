#!/usr/bin/env python3
"""Fetch full-body transparent sprites (all outfits × all expressions) from bluearchive.wiki.

The wiki's `<Character>/gallery` page groups sprites by outfit, and each outfit
lists the sprite indices used in game (e.g. `Momoi_00.png` … `Momoi_99.png`).
Files are full-body PNGs with alpha; expression variants share the same body and
differ only in the face.

Output layout:

    data/characters/<slug>/sprites/<outfit>/<key>.png
    data/characters/<slug>/sprites/manifest.json
    data/characters/<slug>/profile.yaml   (outfits rewritten when --profile is on)

`manifest.json` records source page, game sprite id, outfit variant, each
sprite's key / dimensions / SHA-256 / upstream URL. `profile.yaml` gets one
entry per outfit so the existing prepare/render path can use any expression by
key (and `default` always points at the neutral `00` sprite).

Examples:
    uv run python scripts/fetch_sprites.py list Momoi
    uv run python scripts/fetch_sprites.py get Momoi
    uv run python scripts/fetch_sprites.py get Momoi --slug saiba-momoi --no-profile
    uv run python scripts/fetch_sprites.py get Momoi --contact
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

WIKI = "https://bluearchive.wiki"
API = f"{WIKI}/w/api.php"
USER_AGENT = "ba-shortdrama/1.0 (+local research; bluearchive.wiki)"
CHARACTERS = lib.CHARACTERS
CACHE = lib.ROOT / "local" / "cache" / "bluearchive-wiki"

RIGHTS = (
    "Blue Archive game sprites uploaded to bluearchive.wiki; rights stay with NEXON / "
    "the rights holders. No redistribution or commercial permission verified. "
    "Check https://bluearchive.wiki/wiki/Blue_Archive_Wiki:Copyrights before publishing."
)

# Wiki variant -> production outfit id / Chinese display name.
OUTFIT_NAMES = {
    "": ("default", "标准制服"),
    "Maid": ("maid", "女仆"),
    "Battle": ("battle", "武装"),
    "Winter": ("winter", "防寒服"),
}
# Canonical neutral sprite per outfit. Do not rely on `00`: the battle set uses
# `02` as its neutral pose, and the maid set prefixes every index with `diorama_`.
OUTFIT_DEFAULT_KEYS = {
    "default": "00",
    "maid": "diorama_00",
    "battle": "02",
    "winter": "00",
}
# Human-labelled aliases for the raw sprite indices. The index keys stay the
# source of truth; aliases only make script.json's `emotion` values resolve.
# Labels come from visual review of the wiki sprites (2026-10-23), not from
# official data, so treat them as production conventions.
EXPRESSION_ALIASES = {
    "default": {
        "default": "00", "neutral": "00",
        "happy": "01", "smile": "01",
        "worried": "02", "confused": "02",
        "excited": "03", "laugh": "03",
        "surprised": "04", "shocked": "04",
        "cheerful": "05",
        "sad": "06", "cry": "06",
        "angry": "07", "pout": "07",
        "furious": "08", "shout": "08",
        "smug": "99", "confident": "99",
    },
    "maid": {
        "default": "diorama_00", "neutral": "diorama_00",
        "happy": "diorama_01", "smile": "diorama_01",
        "worried": "diorama_02", "confused": "diorama_02",
        "excited": "diorama_03", "laugh": "diorama_03",
        "surprised": "diorama_04", "shocked": "diorama_04",
        "flustered": "diorama_05",
        "sad": "diorama_10", "cry": "diorama_06",
        "angry": "diorama_07", "pout": "diorama_07",
        "shout": "diorama_08",
        "smug": "diorama_99", "confident": "diorama_99",
    },
    "battle": {
        "default": "02", "neutral": "02",
        "happy": "01", "smile": "01",
        "excited": "00", "cheerful": "18", "laugh": "03",
        "surprised": "21", "shocked": "04",
        "sad": "24", "cry": "06",
        "angry": "07", "pout": "07",
        "determined": "25", "serious": "25",
        "smug": "99", "confident": "99",
    },
    "winter": {
        "default": "00", "neutral": "00",
        "happy": "01", "smile": "01",
        "worried": "02", "confused": "02",
        "excited": "03", "laugh": "03",
        "surprised": "04", "shocked": "04",
        "cheerful": "05",
        "cry": "06", "sad": "24",
        "angry": "07", "pout": "07",
        "shout": "15",
        "smug": "99", "confident": "99",
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch(url: str, timeout: int = 120, retries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            response.raise_for_status()
            return response.content
        except requests.RequestException as error:
            last = error
            if attempt < retries:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"请求失败：{url}（{last}）")


def api(**params) -> dict:
    query = urllib.parse.urlencode({"format": "json", "formatversion": 2, **params})
    return json.loads(fetch(f"{API}?{query}"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wikitext(page: str) -> str:
    payload = api(action="parse", page=page, prop="wikitext")
    if "error" in payload:
        raise SystemExit(f"wiki 页面不存在：{page}（{payload['error'].get('info')}）")
    return payload["parse"]["wikitext"]


def parse_template(text: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for match in re.finditer(r"\|\s*([A-Za-z_]+)\s*=\s*([^|}\n]*)", text):
        params[match.group(1).strip()] = match.group(2).strip()
    return params


def parse_outfits(page_text: str) -> list[dict]:
    """Return outfit sections: variant, game id, type, background, sprite file names."""
    outfits: list[dict] = []
    sections = re.split(r"\n==\s*([^=\n]+?)\s*==\n", page_text)
    # re.split yields [prefix, title, body, title, body, ...]
    for index in range(1, len(sections), 2):
        title, body = sections[index].strip(), sections[index + 1]
        sprite_template = re.search(r"\{\{Sprite\b(.*?)\}\}", body, re.S)
        if not sprite_template:
            continue
        params = parse_template(sprite_template.group(1))
        gallery = re.search(r"<gallery[^>]*>(.*?)</gallery>", body, re.S)
        files = []
        if gallery:
            files = [
                line.strip()
                for line in gallery.group(1).splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        if not files:
            continue
        outfits.append(
            {
                "section": title,
                "game_id": params.get("Id", ""),
                "type": params.get("Type", ""),
                "character": params.get("CharacterName", ""),
                "variant": params.get("CharacterVariant", ""),
                "background": params.get("Background", ""),
                "files": files,
            }
        )
    return outfits


def image_urls(files: list[str]) -> dict[str, dict]:
    """Resolve File: titles to direct URLs, sizes and mime in batches of 50."""
    resolved: dict[str, dict] = {}
    for start in range(0, len(files), 50):
        batch = files[start : start + 50]
        titles = "|".join(f"File:{name}" for name in batch)
        payload = api(action="query", prop="imageinfo", iiprop="url|size|mime", titles=titles)
        for page in payload.get("query", {}).get("pages", []):
            info = (page.get("imageinfo") or [{}])[0]
            if not info.get("url"):
                continue
            # Normalized titles use spaces instead of underscores; map back by name.
            name = page["title"].removeprefix("File:").replace(" ", "_")
            resolved[name] = info
    return resolved


def sprite_key(filename: str) -> str:
    stem = re.sub(r"\.png$", "", filename)
    match = re.search(r"_((?:diorama_)?\d+)$", stem)
    return match.group(1) if match else stem.split("_")[-1]


def resolve_image(resolved: dict[str, dict], filename: str) -> dict | None:
    """Look up an imageinfo entry, tolerating space/underscore title normalization."""
    for candidate in (filename, filename.replace(" ", "_"), filename.replace("_", " ")):
        if candidate in resolved:
            return resolved[candidate]
    return None


def download(url: str, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        return {"path": dest, "size": dest.stat().st_size, "sha256": sha256_file(dest), "reused": True}
    data = fetch(url)
    temporary = dest.with_name(dest.name + ".part")
    temporary.write_bytes(data)
    temporary.replace(dest)
    return {"path": dest, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "reused": False}


def profile_slug(page_name: str) -> str | None:
    """Reuse the kivo summary's English name to find the existing character directory."""
    needle = page_name.strip().lower()
    for directory in sorted(CHARACTERS.iterdir()):
        summary = directory / "kivo" / "summary.json"
        if not summary.is_file():
            continue
        names = (lib.load_json(summary).get("student") or {}).get("names") or {}
        english = (names.get("en") or "").lower()
        if needle in english.split():
            return directory.name
    return re.sub(r"[^a-z0-9]+", "-", page_name.lower()).strip("-") or None


def contact_sheet(sprites: list[dict], out: Path) -> None:
    thumb_height = 220
    margin = 12
    label_height = 26
    thumbs = []
    for entry in sprites:
        with Image.open(entry["local"]) as image:
            image = image.convert("RGBA")
            ratio = thumb_height / image.height
            resized = image.resize((max(1, int(image.width * ratio)), thumb_height), Image.LANCZOS)
            canvas = Image.new("RGBA", resized.size, (235, 235, 235, 255))
            canvas.alpha_composite(resized)
            thumbs.append((entry["key"], canvas))
    width = sum(thumb.width + margin for _, thumb in thumbs) + margin
    sheet = Image.new("RGB", (width, thumb_height + label_height + margin * 2), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    x = margin
    for key, thumb in thumbs:
        sheet.paste(thumb.convert("RGB"), (x, margin))
        draw.text((x + 4, margin + thumb_height + 4), key, fill=(30, 30, 30))
        x += thumb.width + margin
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)


def fetch_character(page_name: str, *, slug: str = "", update_profile: bool = True,
                    contact: bool = False) -> Path:
    page = page_name if "/" in page_name else f"{page_name}/gallery"
    page_text = wikitext(page)
    outfits = parse_outfits(page_text)
    if not outfits:
        raise SystemExit(f"{page} 没有找到立绘分组")

    slug = slug or profile_slug(page_name) or page_name.lower()
    directory = CHARACTERS / slug
    sprites_root = directory / "sprites"

    all_files = [name for outfit in outfits for name in outfit["files"]]
    resolved = image_urls(all_files)
    missing = [name for name in all_files if resolve_image(resolved, name) is None]
    if missing:
        raise SystemExit(
            f"错误：{page} 有 {len(missing)}/{len(all_files)} 个立绘没有解析到图片 URL，"
            "本次不写入 manifest/profile，现有索引保持不变：\n  " + "\n  ".join(missing)
        )
    sprites_root.mkdir(parents=True, exist_ok=True)
    manifest_path = sprites_root / "manifest.json"

    manifest = {
        "schema_version": 1,
        "source": {
            "provider": "bluearchive-wiki",
            "page": f"{WIKI}/wiki/{page}",
            "api": API,
            "fetched_at": now_iso(),
            "rights": RIGHTS,
        },
        "character": {
            "wiki_page": page_name,
            "slug": slug,
            "outfits": [],
        },
    }

    total = 0
    expected_total = len(all_files)
    for outfit in outfits:
        variant = outfit["variant"]
        outfit_id, outfit_name = OUTFIT_NAMES.get(variant, (re.sub(r"[^a-z0-9]+", "-", variant.lower()).strip("-") or "default", variant or "default"))
        outfit_dir = sprites_root / outfit_id
        entries = []
        for filename in outfit["files"]:
            info = resolve_image(resolved, filename)
            if not info:
                raise SystemExit(f"错误：{outfit['section']} 的 {filename} 没有解析到 URL，已中止")
            key = sprite_key(filename)
            dest = outfit_dir / f"{key}.png"
            meta = download(info["url"], dest)
            if not dest.is_file():
                raise SystemExit(f"错误：{filename} 下载后文件不存在：{dest}")
            with Image.open(dest) as image:
                if image.mode not in ("RGBA", "LA"):
                    converted = image.convert("RGBA")
                    converted.save(dest)
                    meta["sha256"] = sha256_file(dest)
                    meta["size"] = dest.stat().st_size
                width, height = image.size
            entries.append(
                {
                    "key": key,
                    "file": str(dest.relative_to(lib.ROOT)),
                    "width": width,
                    "height": height,
                    "size": meta["size"],
                    "sha256": meta["sha256"],
                    "source_name": filename,
                    "url": info["url"],
                    "local": dest,
                }
            )
            total += 1
        if len(entries) != len(outfit["files"]):
            raise SystemExit(
                f"错误：{outfit['section']} 预期 {len(outfit['files'])} 张，实际 {len(entries)} 张，已中止"
            )
        entries.sort(key=lambda entry: (entry["key"] == "99", entry["key"]))
        manifest["character"]["outfits"].append(
            {
                "id": outfit_id,
                "name": outfit_name,
                "section": outfit["section"],
                "game_sprite_id": outfit["game_id"],
                "type": outfit["type"],
                "variant": variant,
                "background": outfit["background"] or None,
                "expected": len(outfit["files"]),
                "sprites": [
                    {key: value for key, value in entry.items() if key != "local"} for entry in entries
                ],
            }
        )
        if contact:
            sheet = CACHE / "contact" / slug / f"{outfit_id}.jpg"
            contact_sheet(entries, sheet)
            print(f"  联系人：{sheet}")
        print(f"  {outfit_name}（{variant or 'default'}）: {len(entries)} 张")

    if total != expected_total:
        raise SystemExit(f"错误：预期 {expected_total} 张立绘，实际写入 {total} 张，已中止")
    manifest["stats"] = {
        "outfits": len(manifest["character"]["outfits"]),
        "sprites": total,
        "expected": expected_total,
    }
    verify_manifest(manifest)
    lib.write_json(manifest_path, manifest)
    print(f"清单：{manifest_path.relative_to(lib.ROOT)}")

    if update_profile:
        update_profile_outfits(directory, manifest)
    return manifest_path


def verify_manifest(manifest: dict) -> None:
    """Fail unless every outfit and every referenced file is complete and intact.

    Called before writing either index, so an incomplete upstream result or a
    damaged local file cannot replace the previous manifest/profile.
    """
    for outfit in manifest["character"]["outfits"]:
        expected = outfit.get("expected")
        if expected is not None and len(outfit["sprites"]) != expected:
            raise SystemExit(
                f"错误：{outfit['id']} 预期 {expected} 张，实际 {len(outfit['sprites'])} 张，"
                "manifest/profile 保持不变"
            )
        if not outfit["sprites"]:
            raise SystemExit(f"错误：{outfit['id']} 没有任何立绘，manifest/profile 保持不变")
        for entry in outfit["sprites"]:
            source = lib.ROOT / entry["file"]
            if not source.is_file():
                raise SystemExit(
                    f"错误：{outfit['id']} 的 {entry['key']} 缺少文件 {source}，"
                    "manifest/profile 保持不变"
                )
            actual = sha256_file(source)
            if actual != entry["sha256"]:
                raise SystemExit(
                    f"错误：{outfit['id']} 的 {entry['key']} 哈希不符"
                    f"（{actual} != {entry['sha256']}），manifest/profile 保持不变"
                )


def update_profile_outfits(directory: Path, manifest: dict) -> None:
    """Merge the fetched outfits into profile.yaml without touching persona/voice.

    Nothing is written unless every outfit matches its expected sprite count and
    every referenced file exists with the recorded SHA-256. A partial upstream
    result therefore leaves the previous profile (including `missing`) intact.
    """
    path = directory / "profile.yaml"
    if not path.is_file():
        print(f"  跳过 profile：{path} 不存在")
        return
    verify_manifest(manifest)
    profile = lib.load_json(path)
    character_prefix = Path("data") / "characters" / directory.name
    outfits = {}
    for outfit in manifest["character"]["outfits"]:
        sprites = {}
        for entry in outfit["sprites"]:
            relative = Path(entry["file"])
            if relative.is_relative_to(character_prefix):
                relative = relative.relative_to(character_prefix)
            sprites[entry["key"]] = {"path": str(relative), "sha256": entry["sha256"]}
        # The neutral sprite is explicit per outfit (battle uses 02, maid uses
        # diorama_00), never an incidental `00` from setdefault order.
        default_key = OUTFIT_DEFAULT_KEYS.get(outfit["id"])
        if default_key is None:
            default_key = EXPRESSION_ALIASES.get(outfit["id"], {}).get("default")
        if default_key not in sprites:
            default_key = "00" if "00" in sprites else next(iter(sprites))
        sprites.setdefault("default", dict(sprites[default_key]))
        # Semantic aliases only for the keys the outfit actually ships.
        for alias, key in EXPRESSION_ALIASES.get(outfit["id"], {}).items():
            if key in sprites:
                sprites.setdefault(alias, dict(sprites[key]))
        outfits[outfit["id"]] = {"name": outfit["name"], "sprites": sprites}
    profile["outfits"] = outfits
    profile["missing"] = []
    lib.write_json(path, profile)
    print(f"  profile：{path.relative_to(lib.ROOT)}（{len(outfits)} 套服装）")


def list_outfits(page_name: str) -> None:
    page = page_name if "/" in page_name else f"{page_name}/gallery"
    outfits = parse_outfits(wikitext(page))
    if not outfits:
        raise SystemExit(f"{page} 没有找到立绘分组")
    for outfit in outfits:
        variant = outfit["variant"] or "default"
        print(
            f"{variant:<8} id={outfit['game_id']:<8} type={outfit['type']:<4} "
            f"{len(outfit['files']):>3} 张  {outfit['section']}"
        )
        print("         " + ", ".join(sprite_key(name) for name in outfit["files"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="从 bluearchive.wiki 获取全身立绘（全部服装 × 全部表情）")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", help="列出页面上的服装与表情索引")
    list_cmd.add_argument("page", help="角色英文名，如 Momoi，或完整页面 Momoi/gallery")

    get_cmd = sub.add_parser("get", help="下载全部服装与表情")
    get_cmd.add_argument("page")
    get_cmd.add_argument("--slug", default="", help="角色目录名，默认从 kivo summary 的英文名推断")
    get_cmd.add_argument("--no-profile", action="store_true", help="只写 manifest，不改 profile.yaml")
    get_cmd.add_argument("--contact", action="store_true", help="额外生成每套服装的缩略图总览")

    args = parser.parse_args()
    if args.command == "list":
        list_outfits(args.page)
        return 0
    fetch_character(args.page, slug=args.slug, update_profile=not args.no_profile, contact=args.contact)
    return 0


if __name__ == "__main__":
    sys.exit(main())
