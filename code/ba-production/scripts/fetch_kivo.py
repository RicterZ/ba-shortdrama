#!/usr/bin/env python3
"""Fetch Blue Archive material from kivo.wiki (基沃托斯古书馆) into this workspace.

Four kinds of material, all from kivo.wiki:

* student info   `/api/v1/data/students/` — profile, school, club, stats, voices
* student art    Live2D spine package (`skel`/`atlas`/texture), avatar and the
                 face-expression diffs shown on the character page
* background music `/api/v1/musics/` — original `.ogg` files
* UI / story SFX  the "游戏内全音效素材速查表" share on cloud.kivo.wiki

Kivo does not publish a flat, transparent full-body standing image: the
character page renders the Live2D spine. The production pipeline needs a flat
sprite, so `student --portrait` optionally pulls the SchaleDB portrait that
matches the kivo English given name. See `RESOURCES.md` for the full contract.

Examples:
    uv run python scripts/fetch_kivo.py student list --name 才羽
    uv run python scripts/fetch_kivo.py student 2 --portrait
    uv run python scripts/fetch_kivo.py music list --match School
    uv run python scripts/fetch_kivo.py music preset
    uv run python scripts/fetch_kivo.py sfx list --match UI_Button
    uv run python scripts/fetch_kivo.py sfx preset
    uv run python scripts/fetch_kivo.py check
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

API = "https://api.kivo.wiki/api/v1"
SITE = "https://kivo.wiki"
STATIC = "https://static.kivo.wiki"
USER_AGENT = "ba-shortdrama/1.0 (+local research; kivo.wiki)"

# Public share that backs kivo's "游戏内全音效素材速查表" article (id 24).
SHARE_HOST = "https://cloud.kivo.wiki"
SHARE_KEY = "vmIj"
SHARE_PASSWORD = "kivowiki"
SHARE_BASE = f"{SHARE_HOST}/api/v3"

SCHALEDB_STUDENTS = (
    "https://raw.githubusercontent.com/SchaleDB/SchaleDB/main/data/cn/students.json"
)
SCHALEDB_PORTRAIT = (
    "https://raw.githubusercontent.com/SchaleDB/SchaleDB/main/images/student/portrait/{id}.webp"
)

AUDIO_DIR = lib.ROOT / "data" / "audio"
AUDIO_MANIFEST = AUDIO_DIR / "manifest.json"
CHARACTERS = lib.CHARACTERS
CACHE = lib.ROOT / "local" / "cache" / "kivo"

RIGHTS = (
    "kivo.wiki 整理的《蔚蓝档案》游戏素材；未核实再分发或商用许可，"
    "公开发布前必须核对权利方政策与 kivo 使用条款（https://kivo.wiki/license）"
)

# A small, useful starter set for the BA-style UI: click, back, confirm,
# notice, chimes, transitions and a few reward/level-up stings.
SFX_PRESET = [
    "UI_Button_Touch",
    "UI_Button_Back",
    "UI_Complete_Check",
    "UI_Bit_Select",
    "UI_Notice",
    "UI_Bubble",
    "UI_Star",
    "UI_Chime_01",
    "UI_Chime_02",
    "UI_Chime_03",
    "UI_Loading",
    "UI_Ready",
    "UI_Transition_Whoosh_ST",
    "UI_Error_Neg",
    "UI_Fade",
    "UI_Unlock",
    "UI_LevelUp",
    "UI_Rank",
    "UI_Pause",
    "UI_Alarm",
]

# Game-loop BGM that suits slice-of-life / comedy episodes.
BGM_PRESET = [1, 7, 3, 4, 5, 14, 2]


# ── HTTP helpers ────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch(url: str, timeout: int = 60, retries: int = 3, headers: dict | None = None) -> bytes:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT, **(headers or {})}, timeout=timeout)
            response.raise_for_status()
            return response.content
        except requests.RequestException as error:
            last = error
            if attempt < retries:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"请求失败：{url}（{last}）")


def api(path: str, **params) -> dict:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    payload = json.loads(fetch(f"{API}{path}{query}"))
    if not payload.get("success", True):
        raise RuntimeError(f"kivo API {path} 返回错误：{payload.get('message') or payload}")
    return payload.get("data") or {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, force: bool = False) -> dict:
    """Download to `dest` atomically; reuse an existing file unless forced."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and not force:
        return {"path": dest, "size": dest.stat().st_size, "sha256": sha256_file(dest), "reused": True}

    temporary = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    size = 0
    with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120, stream=True) as response, temporary.open("wb") as handle:
        response.raise_for_status()
        for chunk in response.iter_content(1 << 20):
            handle.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    if size == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"下载到空文件：{url}")
    temporary.replace(dest)
    return {"path": dest, "size": size, "sha256": digest.hexdigest(), "reused": False}


def relative(path: Path) -> str:
    return str(path.relative_to(lib.ROOT))


# ── kivo student data ───────────────────────────────────────────────────────


def student_list(name: str = "", page_size: int = 100) -> list[dict]:
    students: list[dict] = []
    page = 1
    while True:
        params = {"page": page, "page_size": page_size}
        if name:
            params["name"] = name
        data = api("/data/students/", **params)
        batch = data.get("students") or []
        students.extend(batch)
        if not batch or page >= int(data.get("max_page") or 1):
            break
        page += 1
    return students


def resolve_student(spec: str) -> dict:
    """Accept a kivo student id or a (partial) Chinese / English name."""
    if spec.isdigit():
        return api(f"/data/students/{spec}")
    matches = student_list(name=spec)
    if not matches:
        raise SystemExit(f"kivo 上找不到学生：{spec}")
    if len(matches) > 1:
        lines = [f"{item['id']}\t{item.get('family_name_cn','')}{item.get('given_name_cn','')}\t{item.get('skin_cn') or item.get('skin','')}" for item in matches[:20]]
        raise SystemExit("匹配到多个学生，请改用 id：\n" + "\n".join(lines))
    return api(f"/data/students/{matches[0]['id']}")


def lookup_table(path: str, key: str, force: bool = False) -> dict[int, dict]:
    """Cache small reference tables (schools, relations) for a day."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / f"{key}.json"
    if cache.is_file() and not force and time.time() - cache.stat().st_mtime < 86400:
        rows = json.loads(cache.read_text(encoding="utf-8"))
    else:
        rows = api(path, page=1, page_size=500).get(key) or []
        cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return {row["id"]: row for row in rows}


def student_slug(student: dict) -> str:
    family = (student.get("family_name_en") or "").strip()
    given = (student.get("given_name_en") or "").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", f"{family} {given}".lower()).strip("-")
    if not slug:
        slug = f"kivo-{student['id']}"
    if student.get("skin"):
        slug = f"{slug}-{student['id']}"
    return slug


def prefixed(url: str) -> str:
    return url if url.startswith("http") else f"https:{url}" if url.startswith("//") else url


def fetch_student(spec: str, *, slug: str = "", portrait: bool = False, spine: bool = False,
                  diffs: bool = True, force: bool = False) -> Path:
    student = resolve_student(spec)
    slug = slug or student_slug(student)
    directory = CHARACTERS / slug
    kivo_dir = directory / "kivo"
    kivo_dir.mkdir(parents=True, exist_ok=True)

    raw_path = directory / "originals" / "kivo-student.json"
    lib.write_json(raw_path, student)

    schools = lookup_table("/data/schools/", "school")
    relations = lookup_table("/data/relations/", "relation")
    school = schools.get(student.get("school"), {})
    club = relations.get(student.get("main_relation"), {})

    assets: dict = {"avatar": None, "flat_portrait": None, "expressions": [], "spine": []}
    summary_path = kivo_dir / "summary.json"
    if summary_path.is_file():
        previous = (lib.load_json(summary_path).get("assets") or {})
        if not diffs:
            assets["expressions"] = previous.get("expressions") or []
        if not spine:
            assets["spine"] = previous.get("spine") or []
        if not portrait:
            assets["flat_portrait"] = previous.get("flat_portrait")

    avatar_url = prefixed(student.get("avatar") or "")
    if avatar_url:
        meta = download(avatar_url, kivo_dir / "avatar.png", force=force)
        assets["avatar"] = {"path": relative(meta["path"]), "sha256": meta["sha256"], "size": meta["size"], "url": avatar_url}

    # Face-expression diffs ("初始立绘差分" etc.). Kivo crops the face only;
    # these are expression references, not full-body sprites.
    if diffs:
        for group in student.get("gallery") or []:
            title = group.get("title") or ""
            if "差分" not in title:
                continue
            group_dir = kivo_dir / "expressions" / re.sub(r"[/\\]", "-", title)
            for image_url in group.get("images") or []:
                url = prefixed(image_url)
                name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
                meta = download(url, group_dir / name, force=force)
                entry = {
                    "group": title,
                    "path": relative(meta["path"]),
                    "sha256": meta["sha256"],
                    "size": meta["size"],
                    "url": url,
                }
                try:
                    from PIL import Image
                    with Image.open(meta["path"]) as image:
                        entry["width"], entry["height"] = image.size
                except Exception:  # noqa: BLE001 - dimensions are informational
                    pass
                assets["expressions"].append(entry)

    if spine:
        for spine_id in student.get("spine") or []:
            detail = api(f"/data/spines/{spine_id}")
            name = detail.get("name") or f"spine-{spine_id}"
            spine_dir = kivo_dir / "spine" / name
            files = [detail.get("skel_file"), detail.get("atlas_file"), *(detail.get("images") or [])]
            downloaded = []
            for file_url in [item for item in files if item]:
                url = prefixed(file_url)
                dest = spine_dir / urllib.parse.unquote(url.rsplit("/", 1)[-1])
                meta = download(url, dest, force=force)
                downloaded.append({"path": relative(meta["path"]), "sha256": meta["sha256"], "size": meta["size"], "url": url})
            assets["spine"].append({"id": spine_id, "name": name, "remark": detail.get("remark", ""), "files": downloaded})
            print(f"  脊柱（Live2D）: {name} ({len(downloaded)} 个文件)")

    if portrait:
        assets["flat_portrait"] = fetch_schaledb_portrait(student, kivo_dir / "portrait.webp", force=force)

    voice = student.get("voice") or []
    voice_cn = student.get("voice_cn") or []
    categories: dict[str, int] = {}
    for line in voice:
        category = line.get("category") or "unknown"
        categories[category] = categories.get(category, 0) + 1

    summary = {
        "schema_version": 1,
        "source": {
            "provider": "kivo",
            "api": f"{API}/data/students/{student['id']}",
            "page": f"{SITE}/data/character/{student['id']}",
            "fetched_at": now_iso(),
            "rights": RIGHTS,
        },
        "student": {
            "kivo_id": student["id"],
            "slug": slug,
            "names": {
                "cn": f"{student.get('family_name_cn','')}{student.get('given_name_cn','')}",
                "jp": f"{student.get('family_name_jp','')}{student.get('given_name_jp','')}",
                "en": f"{student.get('given_name_en','')} {student.get('family_name_en','')}".strip(),
                "zh_tw": f"{student.get('family_name_zh_tw','')}{student.get('given_name_zh_tw','')}",
                "kr": f"{student.get('family_name_kr','')}{student.get('given_name_kr','')}",
            },
            "skin": student.get("skin", ""),
            "school": {"id": student.get("school"), "name": school.get("name", ""), "name_cn": school.get("name_cn", "")},
            "club": {"id": student.get("main_relation"), "name": club.get("name", "")},
            "relations": [
                {"id": rel_id, "name": relations.get(rel_id, {}).get("name", "")}
                for rel_id in student.get("relation") or []
            ],
            "profile": {
                "age": student.get("age"),
                "height_cm": student.get("height"),
                "birthday": student.get("birthday"),
                "grade": student.get("grade"),
                "hobby": student.get("hobby"),
                "weapon_type": student.get("weapon_type"),
                "body_shape": student.get("body_shape"),
                "nick_name": student.get("nick_name"),
                "designer": student.get("designer"),
                "illustrator": student.get("illustrator"),
                "character_voice_jp": student.get("character_voice"),
                "character_voice_cn": student.get("character_voice_cn"),
                "release_date": student.get("release_date"),
                "release_date_cn": student.get("release_date_cn"),
                "introduction": student.get("introduction"),
                "introduction_cn": student.get("introduction_cn"),
                "momo_talk_signature": student.get("momo_talk_signature"),
            },
            "combat": [
                {
                    "character_id": item.get("character_id"),
                    "dev_name": item.get("dev_name"),
                    "type": item.get("type"),
                    "attack_attribute": item.get("attack_attribute"),
                    "defensive_attributes": item.get("defensive_attributes"),
                    "team_position": item.get("team_position"),
                    "battlefield_position": item.get("battlefield_position"),
                    "rarity": item.get("rarity"),
                    "limited": item.get("limited"),
                }
                for item in student.get("character_datas") or []
            ],
        },
        "voice": {
            "lines_jp": len(voice),
            "lines_cn": len(voice_cn),
            "categories": categories,
            "note": "语音文件 URL 保留在 originals/kivo-student.json；未下载音频。",
        },
        "assets": assets,
    }
    lib.write_json(summary_path, summary)
    update_character_sources(directory, student, slug)

    print(f"角色：{summary['student']['names']['cn']}（kivo id {student['id']}）→ {slug}")
    print(f"  信息：{relative(raw_path)}")
    print(f"  摘要：{relative(summary_path)}")
    if avatar_url:
        print("  头像：kivo/avatar.png")
    if diffs:
        print(f"  表情差分：{len(assets['expressions'])} 张（仅脸部裁切）")
    if assets["flat_portrait"]:
        print(f"  平面立绘：{relative(Path(lib.ROOT / assets['flat_portrait']['path']))}")
    return summary_path


def update_character_sources(directory: Path, student: dict, slug: str) -> None:
    """Record kivo provenance alongside existing sources without dropping them."""
    path = directory / "sources.yaml"
    document = lib.load_json(path) if path.is_file() else {"checked_at": "", "sources": []}
    sources = [item for item in document.get("sources") or [] if item.get("id") != "kivo"]
    sources.append(
        {
            "id": "kivo",
            "url": f"{SITE}/data/character/{student['id']}",
            "data": f"{API}/data/students/{student['id']}",
            "raw": f"data/characters/{slug}/originals/kivo-student.json",
            "image": prefixed(student.get("avatar") or ""),
            "derived": f"data/characters/{slug}/kivo/summary.json",
            "rights": RIGHTS,
            "publication_approved": False,
        }
    )
    document.update({"checked_at": now_iso()[:10], "sources": sources})
    lib.write_json(path, document)


def fetch_schaledb_portrait(student: dict, dest: Path, force: bool = False) -> dict | None:
    """Match the kivo English given name to SchaleDB's DevName and fetch its flat portrait."""
    if student.get("skin"):
        print("  跳过平面立绘：kivo 皮肤变体不做 SchaleDB 匹配")
        return None
    given = (student.get("given_name_en") or "").strip().lower()
    family = (student.get("family_name_en") or "").strip().lower()
    if not given:
        print("  跳过平面立绘：缺少英文名")
        return None

    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / "schaledb-students.json"
    if cache.is_file() and not force and time.time() - cache.stat().st_mtime < 7 * 86400:
        rows = json.loads(cache.read_text(encoding="utf-8"))
    else:
        rows = json.loads(fetch(SCHALEDB_STUDENTS, timeout=180))
        cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    candidates = [row for row in rows if (row.get("DevName") or "").lower() == given]
    if len(candidates) > 1 and family:
        narrowed = [row for row in candidates if (row.get("PathName") or "").lower().startswith(family[:3])]
        candidates = narrowed or candidates
    if len(candidates) != 1:
        print(f"  跳过平面立绘：SchaleDB 匹配到 {len(candidates)} 个 DevName={given!r}")
        return None

    match = candidates[0]
    url = SCHALEDB_PORTRAIT.format(id=match["Id"])
    meta = download(url, dest, force=force)
    return {
        "path": relative(meta["path"]),
        "sha256": meta["sha256"],
        "size": meta["size"],
        "url": url,
        "schaledb_id": match["Id"],
        "matched_dev_name": match.get("DevName"),
        "note": "kivo 不提供平面全身立绘，此图来自 SchaleDB；按英文名匹配",
    }


# ── kivo music (BGM) ────────────────────────────────────────────────────────


def music_catalog() -> list[dict]:
    tracks: list[dict] = []
    page = 1
    while True:
        data = api("/musics/", page=page, page_size=1000)
        batch = data.get("music") or []
        tracks.extend(batch)
        if not batch or page >= int(data.get("max_page") or 1):
            break
        page += 1
    return tracks


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value or "track"


def music_matches(tracks: list[dict], needle: str) -> list[dict]:
    lowered = needle.strip().lower()
    exact = [track for track in tracks if (track.get("title") or "").lower() == lowered]
    if exact:
        return exact
    return [
        track
        for track in tracks
        if lowered in (track.get("title") or "").lower()
        or lowered in (track.get("original_file_name") or "").lower()
    ]


def fetch_music(specs: list[str], force: bool = False) -> None:
    catalog = music_catalog()
    chosen: list[dict] = []
    for spec in specs:
        if spec.isdigit():
            detail = api(f"/musics/{spec}")
            chosen.append(detail)
            continue
        matches = music_matches(catalog, spec)
        if not matches:
            raise SystemExit(f"找不到曲目：{spec}")
        if len(matches) > 1:
            listing = "\n".join(f"{t['id']}\t{t['title']}\t{t.get('use','')}" for t in matches[:15])
            raise SystemExit(f"{spec} 匹配到多首，请改用 id：\n{listing}")
        chosen.append(api(f"/musics/{matches[0]['id']}"))

    entries = []
    for track in chosen:
        file_url = prefixed(track.get("file") or "")
        if not file_url:
            file_url = f"{STATIC}/musics/{urllib.parse.quote(track.get('original_file_name') or '')}.ogg"
        suffix = Path(urllib.parse.unquote(file_url)).suffix or ".ogg"
        dest = AUDIO_DIR / "bgm" / f"{int(track['id']):04d}-{slugify(track['title'])}{suffix}"
        meta = download(file_url, dest, force=force)
        entries.append(
            {
                "id": f"bgm-{int(track['id']):04d}",
                "kind": "bgm",
                "title": track.get("title", ""),
                "path": relative(meta["path"]),
                "format": suffix.lstrip("."),
                "size": meta["size"],
                "sha256": meta["sha256"],
                "source": "kivo-music",
                "source_url": file_url,
                "page": f"{SITE}/music/{track['id']}",
                "upstream_id": track["id"],
                "original_file_name": track.get("original_file_name", ""),
                "album": track.get("album", ""),
                "use": track.get("use", ""),
                "author": track.get("author", ""),
                "rights": RIGHTS,
                "downloaded_at": now_iso(),
            }
        )
        print(f"BGM: {track['id']:>4} {track['title']} ({track.get('use','')}) → {relative(meta['path'])}")
    update_manifest(entries)


# ── kivo cloud SFX share ───────────────────────────────────────────────────


class KivoShare:
    """Session for the Cloudreve public share behind the SFX article."""

    def __init__(self, key: str = SHARE_KEY, password: str = SHARE_PASSWORD) -> None:
        self.key = key
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Referer": f"{SHARE_HOST}/s/{key}"})
        self._unlocked = False

    def _request(self, url: str, method: str = "GET") -> dict:
        response = self.session.request(method, url, timeout=60)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"kivo share 返回错误：{payload}")
        return payload.get("data") or {}

    def unlock(self) -> None:
        if self._unlocked:
            return
        query = urllib.parse.urlencode({"password": self.password})
        data = self._request(f"{SHARE_BASE}/share/info/{self.key}?{query}")
        if data.get("locked", True):
            raise SystemExit("kivo 音效分享仍处于锁定状态，密码或分享链接可能已变更")
        self._unlocked = True

    def objects(self, path: str = "/") -> list[dict]:
        self.unlock()
        query = urllib.parse.urlencode({"path": path})
        data = self._request(f"{SHARE_BASE}/share/list/{self.key}/?{query}")
        return data.get("objects") or []

    def download_url(self, path: str) -> str:
        self.unlock()
        query = urllib.parse.urlencode({"path": path})
        response = self.session.put(f"{SHARE_BASE}/share/download/{self.key}?{query}", timeout=60)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0 or not payload.get("data"):
            raise RuntimeError(f"kivo share 没有返回下载地址：{payload}")
        return payload["data"]


def sfx_catalog(force: bool = False) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / "sfx-catalog.json"
    if cache.is_file() and not force and time.time() - cache.stat().st_mtime < 7 * 86400:
        return json.loads(cache.read_text(encoding="utf-8"))
    share = KivoShare()
    objects = share.objects("/")
    catalog = [
        {
            "name": item["name"],
            "size": item.get("size", 0),
            "category": item["name"].split("_")[0],
            "path": item.get("path", "/"),
        }
        for item in objects
        if item.get("type") == "file" and item["name"].lower().endswith(".wav")
    ]
    cache.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    return catalog


def fetch_sfx(names: list[str], force: bool = False) -> None:
    catalog = sfx_catalog()
    available = {item["name"]: item for item in catalog}
    missing = [name for name in names if name not in available and f"{name}.wav" not in available]
    if missing:
        raise SystemExit("kivo 音效库里没有这些素材：\n" + "\n".join(missing))

    share = KivoShare()
    entries = []
    for name in names:
        key = name if name in available else f"{name}.wav"
        item = available[key]
        dest = AUDIO_DIR / "sfx" / key
        if dest.is_file() and not force:
            meta = {"path": dest, "size": dest.stat().st_size, "sha256": sha256_file(dest), "reused": True}
        else:
            url = share.download_url(f"/{key}")
            meta = download(url, dest, force=True)
        entries.append(
            {
                "id": f"sfx-{dest.stem.lower()}",
                "kind": "sfx",
                "title": dest.stem,
                "path": relative(meta["path"]),
                "format": "wav",
                "size": meta["size"],
                "sha256": meta["sha256"],
                "source": "kivo-sfx-share",
                "source_url": f"{SHARE_HOST}/s/{SHARE_KEY}",
                "share_path": f"/{key}",
                "category": item.get("category", ""),
                "rights": RIGHTS,
                "downloaded_at": now_iso(),
            }
        )
        print(f"SFX: {dest.stem} → {relative(meta['path'])}")
    update_manifest(entries)


# ── audio manifest ─────────────────────────────────────────────────────────


def load_manifest() -> dict:
    if AUDIO_MANIFEST.is_file():
        return lib.load_json(AUDIO_MANIFEST)
    return {"schema_version": 1, "entries": []}


def update_manifest(entries: list[dict]) -> None:
    manifest = load_manifest()
    by_id = {entry["id"]: entry for entry in manifest.get("entries") or []}
    for entry in entries:
        by_id[entry["id"]] = entry
    merged = sorted(by_id.values(), key=lambda item: (item.get("kind", ""), item.get("id", "")))
    counts: dict[str, int] = {}
    for entry in merged:
        counts[entry.get("kind", "")] = counts.get(entry.get("kind", ""), 0) + 1
    manifest = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "sources": {
            "bgm": {"provider": "kivo", "api": f"{API}/musics/", "page": f"{SITE}/music"},
            "sfx": {"provider": "kivo", "share": f"{SHARE_HOST}/s/{SHARE_KEY}", "article": f"{SITE}/article/24"},
        },
        "rights": RIGHTS,
        "stats": {"total": len(merged), **counts},
        "entries": merged,
    }
    lib.write_json(AUDIO_MANIFEST, manifest)
    print(f"清单：{relative(AUDIO_MANIFEST)}（{len(merged)} 条）")


def check_manifest() -> int:
    manifest = load_manifest()
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("manifest.schema_version 必须是 1")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("manifest.entries 为空")
        entries = []

    seen_paths: dict[str, str] = {}
    for entry in entries:
        label = entry.get("id") or entry.get("path") or "?"
        for field in ("id", "kind", "path", "sha256", "size", "source"):
            if field not in entry:
                errors.append(f"{label} 缺少字段 {field}")
        path = lib.ROOT / str(entry.get("path", ""))
        if not path.is_file():
            errors.append(f"{label} 文件不存在：{entry.get('path')}")
            continue
        if path.stat().st_size != entry.get("size"):
            errors.append(f"{label} 大小不一致：{path.stat().st_size} != {entry.get('size')}")
        if sha256_file(path) != entry.get("sha256"):
            errors.append(f"{label} SHA-256 不一致")
        with path.open("rb") as handle:
            magic = handle.read(4)
        if entry.get("kind") == "sfx" and magic != b"RIFF":
            errors.append(f"{label} 不是 WAV")
        if entry.get("kind") == "bgm" and magic not in (b"OggS", b"ID3\x03", b"ID3\x04"):
            errors.append(f"{label} 不是可识别的 OGG/MP3")
        if entry.get("path") in seen_paths:
            errors.append(f"{label} 与 {seen_paths[entry.get('path')]} 指向同一文件")
        seen_paths[entry.get("path", "")] = label

    for error in errors:
        print(f"错误：{error}")
    counts = manifest.get("stats") or {}
    print(f"检查 {len(entries)} 条音频：bgm {counts.get('bgm', 0)}，sfx {counts.get('sfx', 0)}")
    print("通过" if not errors else f"失败：{len(errors)} 个问题")
    return 0 if not errors else 1


# ── CLI ────────────────────────────────────────────────────────────────────


def print_students(rows: list[dict]) -> None:
    for row in rows:
        skin = row.get("skin_cn") or row.get("skin") or ""
        print(
            f"{row['id']:>5}  {row.get('family_name_cn','')}{row.get('given_name_cn',''):<4}"
            f"  {row.get('given_name_en',''):<10} {row.get('family_name_en',''):<12} {skin}"
        )


def print_tracks(rows: list[dict]) -> None:
    for row in rows:
        print(
            f"{row['id']:>5}  {row.get('title',''):<44}  {row.get('use',''):<18}"
            f"  {row.get('album','')}"
        )


def print_sfx(rows: list[dict]) -> None:
    for row in rows:
        print(f"{row['name']:<44} {row['size']:>9}  {row.get('category','')}")


def main() -> int:
    # `student 2` is the common form; expand it to `student get 2`.
    if len(sys.argv) >= 3 and sys.argv[1] == "student" and sys.argv[2] not in ("list", "get", "-h", "--help"):
        sys.argv.insert(2, "get")

    parser = argparse.ArgumentParser(description="从 kivo.wiki 获取 BA 角色、BGM 和音效素材")
    sub = parser.add_subparsers(dest="command", required=True)

    student_cmd = sub.add_parser("student", help="角色信息与立绘")
    student_sub = student_cmd.add_subparsers(dest="student_command", required=True)
    list_cmd = student_sub.add_parser("list", help="列出 / 搜索学生")
    list_cmd.add_argument("--name", default="", help="中文姓名片段，留空列出全部")
    list_cmd.add_argument("--limit", type=int, default=0)
    get_cmd = student_sub.add_parser("get", help="下载一个角色的信息与素材")
    get_cmd.add_argument("spec", help="kivo 学生 id 或中文名")
    get_cmd.add_argument("--slug", default="", help="输出目录名，默认 <family>-<given> 英文小写")
    get_cmd.add_argument("--portrait", action="store_true", help="额外从 SchaleDB 取平面全身立绘")
    get_cmd.add_argument("--spine", action="store_true", help="下载 Live2D spine 立绘包")
    get_cmd.add_argument("--no-diffs", action="store_true", help="不下载表情差分")
    get_cmd.add_argument("--force", action="store_true")

    music_cmd = sub.add_parser("music", help="BGM（kivo 音乐库）")
    music_sub = music_cmd.add_subparsers(dest="music_command", required=True)
    mlist = music_sub.add_parser("list", help="列出曲目")
    mlist.add_argument("--match", default="", help="标题 / 原文件名片段")
    mlist.add_argument("--limit", type=int, default=40)
    mget = music_sub.add_parser("get", help="按 id 或标题下载")
    mget.add_argument("specs", nargs="+")
    mget.add_argument("--force", action="store_true")
    mpre = music_sub.add_parser("preset", help="下载短剧起步 BGM 合集")
    mpre.add_argument("--force", action="store_true")

    sfx_cmd = sub.add_parser("sfx", help="UI / 剧情音效（kivo 音效分享）")
    sfx_sub = sfx_cmd.add_subparsers(dest="sfx_command", required=True)
    slist = sfx_sub.add_parser("list", help="列出音效")
    slist.add_argument("--match", default="", help="名称片段，如 UI_Button")
    slist.add_argument("--limit", type=int, default=80)
    slist.add_argument("--refresh", action="store_true", help="刷新远端目录缓存")
    sget = sfx_sub.add_parser("get", help="按名称下载音效")
    sget.add_argument("names", nargs="+")
    sget.add_argument("--force", action="store_true")
    spre = sfx_sub.add_parser("preset", help="下载 BA 界面常用音效合集")
    spre.add_argument("--force", action="store_true")

    sub.add_parser("check", help="校验 data/audio/manifest.json 与文件哈希")

    args = parser.parse_args()

    if args.command == "student":
        if args.student_command == "list":
            rows = student_list(name=args.name)
            if args.limit:
                rows = rows[: args.limit]
            print_students(rows)
            return 0
        fetch_student(
            args.spec,
            slug=args.slug,
            portrait=args.portrait,
            spine=args.spine,
            diffs=not args.no_diffs,
            force=args.force,
        )
        return 0

    if args.command == "music":
        if args.music_command == "list":
            rows = music_catalog()
            if args.match:
                rows = music_matches(rows, args.match)
            if args.limit:
                rows = rows[: args.limit]
            print_tracks(rows)
            return 0
        if args.music_command == "preset":
            fetch_music([str(item) for item in BGM_PRESET], force=args.force)
            return 0
        fetch_music(args.specs, force=args.force)
        return 0

    if args.command == "sfx":
        if args.sfx_command == "list":
            rows = sfx_catalog(force=args.refresh)
            if args.match:
                needle = args.match.lower()
                rows = [row for row in rows if needle in row["name"].lower()]
            if args.limit:
                rows = rows[: args.limit]
            print_sfx(rows)
            return 0
        if args.sfx_command == "preset":
            fetch_sfx(SFX_PRESET, force=args.force)
            return 0
        fetch_sfx(args.names, force=args.force)
        return 0

    if args.command == "check":
        return check_manifest()

    return 1


if __name__ == "__main__":
    sys.exit(main())
