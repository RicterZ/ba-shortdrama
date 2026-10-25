"""Install a portable BA draft into Bcut's draft directory. Close Bcut first."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path


def default_draft_root():
    """必剪偏好设置里的草稿目录。Windows 和 macOS 的出厂位置不一样。"""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Movies" / "Bcut Drafts"
    return home / "Documents" / "Bcut Drafts"


def caption_font(explicit=None):
    """Resolve on the receiving computer, never retain the exporter's font path."""
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ValueError(f"Caption font does not exist: {path}")
        return path.resolve().as_posix()
    candidates = []
    if sys.platform == "darwin":
        candidates.append(Path('/Applications/BCUT.app/Contents/Resources/Font/Source Han Sans CN Medium.ttf'))
    else:
        for base in (os.environ.get('LOCALAPPDATA'), os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)')):
            if base:
                candidates.extend(Path(base).glob('**/Font/Source Han Sans CN Medium.ttf'))
    for path in candidates:
        if path.is_file():
            return path.resolve().as_posix()
    raise ValueError('Bcut caption font not found; pass --font-path pointing to a Chinese TTF font.')


def install(bundle, root, font_path=None):
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "ba-bcut-1":
        raise ValueError("Not a BA Bcut bundle")
    draft = json.loads((bundle / "draft.bjson").read_text(encoding="utf-8"))
    root.mkdir(parents=True, exist_ok=True)
    # Serializes this installer only; the caller must close Bcut to stop autosave.
    lock = root / ".ba-import.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    stage = None
    try:
        guid = str(uuid.uuid4()).upper()
        target = root / guid
        index = root / "draftInfo.json"
        before = index.read_bytes() if index.exists() else None
        info = json.loads(before.decode("utf-8-sig")) if before else {"draftInfos": []}
        if not isinstance(info.get("draftInfos"), list):
            raise ValueError("Unexpected draftInfo.json; no changes made")

        resolved_font = None

        def relocate(value):
            nonlocal resolved_font
            if isinstance(value, dict):
                return {k: relocate(v) for k, v in value.items()}
            if isinstance(value, list):
                return [relocate(v) for v in value]
            if isinstance(value, str) and value.startswith("__BA_ASSETS__/"):
                name = value.removeprefix("__BA_ASSETS__/")
                if Path(name).name != name or "\\" in name or not (bundle / "assets" / name).is_file():
                    raise ValueError("Invalid or missing bundle asset")
                return (target / "assets" / name).as_posix()
            if isinstance(value, str) and value.startswith("__BCUT_FONT__/"):
                if resolved_font is None:
                    resolved_font = caption_font(font_path)
                return resolved_font
            return value

        draft = relocate(draft)
        stage = Path(tempfile.mkdtemp(dir=root))
        try:
            shutil.copytree(bundle / "assets", stage / "assets")
            cover = bundle / "cover.jpg"
            if cover.is_file():
                shutil.copyfile(cover, stage / "cover.jpg")
            filename = time.strftime("%H-%M-%S") + f"-000--{{{uuid.uuid4()}}}.bjson"
            (stage / filename).write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
            (stage / ".ba-created").write_text("ba-bcut-1\n", encoding="utf-8")
            info["draftInfos"].append({"cloud_draft_id": "", "cloud_draft_version": "",
                "duration": manifest["duration_ms"] * 1000, "id": guid,
                "modifyTime": round(time.time()*1000), "name": manifest["name"], "storyLineId": ""})
            pending = stage / "index.tmp"
            pending.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
            if (index.read_bytes() if index.exists() else None) != before:
                raise RuntimeError("Bcut index changed during import; close Bcut and retry")
            if before is not None:
                (root / f"draftInfo.{guid}.bak").write_bytes(before)
            stage.rename(target)
            stage = None
            # Keep an unindexed new draft on failure; never delete an existing draft.
            os.replace(target / "index.tmp", index)
        except Exception:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
            raise
        return target
    finally:
        os.close(fd)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft-root", type=Path, default=default_draft_root(),
                        help="必剪偏好设置里的草稿目录")
    parser.add_argument("--bcut-closed", action="store_true", help="Confirm Bcut is fully closed")
    parser.add_argument("--font-path", type=Path, help="Installed Chinese TTF font for editable captions")
    args = parser.parse_args()
    if not args.bcut_closed:
        parser.error("Close Bcut completely, then pass --bcut-closed")
    print(install(Path(__file__).resolve().parent, args.draft_root.resolve(), args.font_path))
    print("Start Bcut and open the new draft. Keep the installed assets directory.")


if __name__ == "__main__":
    main()
