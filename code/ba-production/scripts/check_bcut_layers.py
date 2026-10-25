"""Compare reassembled layer pixels against the normal production composition."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import tempfile

from PIL import Image, ImageChops, ImageStat

import lib
from render_bcut_layers import render_layers, default_layers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True)
    args = parser.parse_args()
    episode = lib.resolve_episode(args.episode)
    original = json.loads((episode / "project" / "scene.json").read_text())
    scene = copy.deepcopy(original)
    scene["episode"].update(durationInFrames=80)
    scene["intro"] = None
    first = copy.deepcopy(scene["shots"][0])
    first.update(durationInFrames=45, transition=None)
    first["from"] = 0
    first["lines"] = [copy.deepcopy(first["lines"][0])] if first.get("lines") else []
    if first["lines"]:
        first["lines"][0].update(durationInFrames=8)
        first["lines"][0]["from"] = 0
    if first.get("characters") and first["lines"]:
        extra = copy.deepcopy(first["characters"][0])
        original_id = extra["id"]
        extra.update(id="bcut-test-second", x=0.2)
        scene["characters"][extra["id"]] = copy.deepcopy(scene["characters"][original_id])
        first["characters"].append(extra)
        other_line = copy.deepcopy(first["lines"][0])
        other_line.update(id="bcut-test-second-line", speaker=extra["id"], durationInFrames=26)
        other_line["from"] = 12
        first["lines"].append(other_line)
    second = copy.deepcopy(first)
    second.update(id="bcut-layer-transition", durationInFrames=40,
        transition={"type": "fade", "durationInFrames": 5})
    second["from"] = 40
    for line in second["lines"]:
        line["from"] += 40
        line["durationInFrames"] = min(line["durationInFrames"], 80 - line["from"])
    if second.get("characters"):
        second["characters"][0]["x"] = 0.3
    scene["shots"] = [first, second]
    for shot in scene["shots"]:
        shot["buttons"] = [{"label": "底部按钮", "x": .5, "y": .8, "pressFrame": 16},
                           {"label": "顶部按钮", "x": .2, "y": .06},
                           {"label": "投票处按钮", "x": .2, "y": .65}]
        shot["choices"] = {"options": ["第一项", "第二项", "第三项"],
                           "fromFrame": 0, "selectFrame": 18, "hideFrame": 38}

    scratch = lib.ROOT / "temp" / "bcut-layers"
    scratch.mkdir(parents=True, exist_ok=True)
    for template, style in (("official", "ba"), ("who-is-the-spy", "meme"), ("who-is-the-spy", "ba")):
        scene["episode"]["template"] = template
        scene["episode"].setdefault("style", {})["caption_style"] = style
        if template == "who-is-the-spy":
            scene["intro"] = {"durationInFrames": 6, "title": "片头层级验证"}
            for shot in scene["shots"]:
                shot["voteTags"] = [{"speaker": shot["characters"][-1]["id"], "text": "投票测试"}]
                for entry in shot["characters"]:
                    entry["label"] = {"text": "测试词牌"}
            if second["lines"]:
                second["lines"][0]["kind"] = "thought"
                second["focus"] = second["lines"][0]["speaker"]
        layers = default_layers(scene)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            assets = Path(directory)
            spans = render_layers(scene, episode / "raws", assets, [*layers, "reference"])
            for frame in (0, 8, 12, 35, 39, 40, 42, 44, 45, 50, 75, 79):
                canvas = Image.new("RGBA", (scene["episode"]["width"], scene["episode"]["height"]))
                for layer in [*layers, "transition"]:
                    active = [span for span in spans if span["layer"] == layer and
                              span["startFrame"] <= frame < span["endFrame"]]
                    assert len(active) <= 1, (layer, frame, "overlapping clips")
                    if active:
                        with Image.open(assets / active[0]["name"]) as image:
                            canvas = Image.alpha_composite(canvas, image.convert("RGBA"))
                reference = next(span for span in spans if span["layer"] == "reference" and
                                 span["startFrame"] <= frame < span["endFrame"])
                with Image.open(assets / reference["name"]) as image:
                    difference = ImageChops.difference(canvas.convert("RGB"), image.convert("RGB"))
                maximum = max(hi for _, hi in difference.getextrema())
                mean = max(ImageStat.Stat(difference).mean)
                if maximum > 5 or mean >= 0.6:
                    canvas.save(scratch / "failed-composite.png")
                    with Image.open(assets / reference["name"]) as image:
                        image.save(scratch / "failed-reference.png")
                assert maximum <= 5 and mean < 0.6, (template, frame, maximum, mean)
                print(f"{template}/{style} frame {frame}: max={maximum}, mean={mean:.4f}")
    print("Layer composition and transition comparisons passed.")


if __name__ == "__main__":
    main()
