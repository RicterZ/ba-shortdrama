"""Fetch pinned BA Shy artwork and its named SFX without overwriting resources."""
import hashlib
import json
from pathlib import Path
import requests
import lib
import fetch_kivo

REVISION = "4ddc9ee241f6028d724346acda190155dc98aaf6"
BASE = f"https://raw.githubusercontent.com/ba-archive/blue-archive/{REVISION}/apps/blue-archive-story-editor/src/assets/emotions/"


def main():
    folder = lib.ROOT / "data/effects/ba"
    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in ["Emoticon_Balloon_N.png", "Emoticon_Shy.png"]:
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
    manifest = folder / "shy-sources.json"
    if not manifest.exists():
        manifest.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    fetch_kivo.fetch_sfx(["SFX_Emoticon_Motion_Shy.wav"])


if __name__ == "__main__":
    main()
