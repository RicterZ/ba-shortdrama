"""Pack animated PNG spans into lossless alpha MOV clips; static holds stay images.

Thousands of individually registered PNG files exhaust Bcut's open-file limit.
QuickTime Animation keeps RGBA pixels exact while bounding the resource count.
Only runs of short, changing frames are packed. A frame held for at least half a
second remains a PNG clip so a still sprite, background or caption stays an image.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import av

MIN_PACKED_SPANS = 8


def encode(group, layer, fps, assets):
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("ffmpeg is required to encode Bcut transparent animation layers")
    frames = group[-1]["endFrame"] - group[0]["startFrame"]
    key = json.dumps([(s["name"], s["endFrame"] - s["startFrame"]) for s in group]) + str(fps) + "image2pipe-v2"
    name = "animation-" + hashlib.sha256(key.encode()).hexdigest()[:24] + ".mov"
    destination = Path(assets) / name
    if not destination.exists():
        print(f"Bcut: encoding {layer} {group[0]['startFrame']}-{group[-1]['endFrame']} alpha MOV", flush=True)
        with tempfile.TemporaryDirectory(dir=assets) as temporary:
            pending = Path(temporary) / name
            process = subprocess.Popen([executable, "-hide_banner", "-loglevel", "error", "-nostdin",
                "-f", "image2pipe", "-framerate", str(fps), "-vcodec", "png", "-i", "pipe:0",
                "-an", "-c:v", "qtrle", "-pix_fmt", "argb", "-frames:v", str(frames),
                str(pending)], stdin=subprocess.PIPE)
            try:
                for span in group:
                    content = (Path(assets) / span["name"]).read_bytes()
                    for _ in range(span["endFrame"] - span["startFrame"]):
                        process.stdin.write(content)
                process.stdin.close()
                if process.wait() != 0:
                    raise RuntimeError("Bcut alpha video encoding failed")
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait()
            with av.open(str(pending)) as container:
                stream = container.streams.video[0]
                if stream.frames != frames or stream.average_rate != fps:
                    raise RuntimeError("Bcut alpha video frame count/rate mismatch")
            pending.rename(destination)
    return {**group[0], "endFrame": group[-1]["endFrame"], "name": name, "media": "video"}


def compact_layers(spans, scene, assets):
    fps = scene["episode"]["fps"]
    hold = max(2, fps // 2)
    boundaries = sorted({0, scene["episode"]["durationInFrames"],
                         *(shot["from"] for shot in scene["shots"])})
    result = []
    # Preserve layer stacking order, even when some layers have gaps.
    for layer in dict.fromkeys(span["layer"] for span in spans):
        selected = sorted((s for s in spans if s["layer"] == layer), key=lambda s: s["startFrame"])
        for start, end in zip(boundaries, boundaries[1:]):
            fragments = [{**s, "startFrame": max(start, s["startFrame"]),
                          "endFrame": min(end, s["endFrame"])} for s in selected
                         if s["startFrame"] < end and s["endFrame"] > start]
            runs = []
            for span in fragments:
                still = span["endFrame"] - span["startFrame"] >= hold
                touching = runs and runs[-1][-1]["endFrame"] == span["startFrame"]
                if still or not touching or runs[-1][-1]["endFrame"] - runs[-1][-1]["startFrame"] >= hold:
                    runs.append([span])
                else:
                    runs[-1].append(span)
            for run in runs:
                if len(run) < MIN_PACKED_SPANS:
                    result.extend(run)
                else:
                    result.append(encode(run, layer, fps, assets))
    return result
