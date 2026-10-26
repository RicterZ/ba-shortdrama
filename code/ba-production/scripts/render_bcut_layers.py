"""Reuse production Remotion components as independently editable PNG layer spans.

The caller owns the episode lock and an existing assets directory. Animated frames
are never subsampled: typewriter/cursor animations, entrance, action, bubbles and
transitions run at the source frame rate. Proven static states reuse a rendered
frame, and identical consecutive frames share a single clip.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image

import lib
from render import BA_PRODUCTION, remotion_env


from bcut_processor import load_processor


def render_layers(scene, raws, output_assets, layers=None, *, editable_captions=False, concurrency=None):
    processor = load_processor(scene)
    if hasattr(processor, "images"):
        from image_layout import render_images
        if layers is not None:
            raise ValueError("Image processors do not expose Remotion layer selection")
        return render_images(scene, Path(raws), Path(output_assets), processor.images(scene))
    if editable_captions:
        scene = {**scene, "bcutHideDialogueText": True}
    if layers is None:
        layers = processor.layers(scene, editable_captions)
    transitions = processor.composites(scene) if hasattr(processor, "composites") else []
    merged = []
    for start, end in sorted(transitions):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    transitions = merged
    scratch_root = lib.ROOT / "temp" / "bcut-layers"
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch_root) as directory:
        scratch = Path(directory)
        request = scratch / "request.json"
        result = scratch / "result.json"
        request.write_text(json.dumps({"scene": scene, "raws": str(Path(raws).resolve()),
            "assets": str(Path(output_assets).resolve()), "scratch": str(scratch),
            "layers": layers, "transitions": transitions, "result": str(result),
            "concurrency": concurrency, "jobs": render_jobs(scene, layers, transitions)}, ensure_ascii=False), encoding="utf-8")
        subprocess.run([os.environ.get("NODE") or "node",
            str(Path(__file__).with_suffix(".mjs")), str(request)],
            cwd=BA_PRODUCTION, env=remotion_env(), check=True)
        spans = json.loads(result.read_text(encoding="utf-8"))
    # Transparent frames carry no edit information. Drop them, keeping gaps exact.
    visible = {}
    for span in spans:
        name = span["name"]
        if name not in visible:
            with Image.open(Path(output_assets) / name) as image:
                visible[name] = image.convert("RGBA").getchannel("A").getbbox() is not None
    return [span for span in spans if visible[span["name"]]]


def default_layers(scene, editable_captions=False):
    return load_processor(scene).layers(scene, editable_captions)


def layer_frame_ranges(scene, layers, transitions=()):
    processor = load_processor(scene)
    if hasattr(processor, "ranges"):
        return processor.ranges(scene, layers, transitions)
    total = scene["episode"]["durationInFrames"]
    result = {}
    for layer in layers:
        ranges = [[0, total]]
        if layer not in {"reference", "transition"}:
            for a, b in transitions:
                ranges = [[start, end] for x, y in ranges
                          for start, end in ((x, min(a, y)), (max(b, x), y)) if end > start]
        result[layer] = ranges
    return result


def render_jobs(scene, layers, transitions=()):
    processor = load_processor(scene)
    if hasattr(processor, "jobs"):
        return processor.jobs(scene, layers, transitions)
    # New templates render every frame unless their processor explicitly opts in.
    jobs = [{"layer": layer, "start": a, "end": b}
            for layer, ranges in layer_frame_ranges(scene, layers, transitions).items()
            for a, b in ranges]
    return jobs + [{"layer": "transition", "start": a, "end": b} for a, b in transitions]


def effect_audio_events(scene):
    processor = load_processor(scene)
    return processor.effects(scene) if hasattr(processor, "effects") else []
