"""Fetch pinned BA bubble artwork and named SFX without overwriting resources."""
import hashlib
import json
from pathlib import Path
import requests
import lib
import fetch_kivo

REVISION = "4ddc9ee241f6028d724346acda190155dc98aaf6"
BASE = f"https://raw.githubusercontent.com/ba-archive/blue-archive/{REVISION}/apps/blue-archive-story-editor/src/assets/emotions/"
PRESETS = json.loads((Path(__file__).resolve().parents[1] / "templates/bubble-presets.json").read_text())


def main():
    folder = lib.ROOT / "data/effects/ba"
    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in sorted({image for preset in PRESETS.values() for image in preset["images"]}):
        dest = folder / name
        if not dest.exists():
            response = requests.get(BASE + name, timeout=60)
            response.raise_for_status()
            if not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
                raise SystemExit(f"Not a PNG: {name}")
            with dest.open("xb") as stream:
                stream.write(response.content)
        entries.append({"path": name, "url": BASE + name,
                        "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
                        "rights": "Blue Archive assets belong to their respective owners; not relicensed by this project"})
    manifest = folder / "bubble-sources.json"
    existing = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    known = {item["path"] for item in existing}
    additions = [item for item in entries if item["path"] not in known]
    if additions:
        manifest.write_text(json.dumps(existing + additions, indent=2) + "\n", encoding="utf-8")
    fetch_kivo.fetch_sfx([f"SFX_Emoticon_Motion_{name}.wav" for name in PRESETS])


if __name__ == "__main__":
    main()
