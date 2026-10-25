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


def default_layers(scene, editable_captions=False):
    """Match CSS stacking contexts, including overlays that interleave by z-index."""
    count = max((len(shot.get("characters", [])) for shot in scene["shots"]), default=0)
    characters = [f"character-slot:{slot}" for slot in range(count)]
    layers = ["background", *characters]
    if scene["episode"].get("template", "official") == "official":
        layers += ["dialogue" if editable_captions else "dialogue-full",
                   "choices", "buttons", "chrome"]
    elif editable_captions:
        layers = ["background", "dialogue-ba", *characters, "choices", "buttons", "chrome"]
    else:
        # Spy character wrappers use z=3/6, above the z=auto BA dialogue.
        layers = ["background", "dialogue-ba", *characters, "word-labels", "choices",
                  "votes", "buttons", "thought", "meme", "chrome"]
    if scene.get("intro"):
        layers.append("intro")
    return layers


def render_layers(scene, raws, output_assets, layers=None, *, editable_captions=False, concurrency=None):
    template = scene["episode"].get("template", "official")
    if template not in {"official", "who-is-the-spy"}:
        raise ValueError("Unsupported production template")
    if editable_captions:
        scene = {**scene, "bcutHideDialogueText": True}
    if layers is None:
        layers = default_layers(scene, editable_captions)
    transitions = []
    for shot in scene["shots"][1:]:
        transition = shot.get("transition")
        if transition and transition.get("type") != "none":
            start = int(shot["from"])
            end = min(scene["episode"]["durationInFrames"], start + int(transition["durationInFrames"]))
            if end > start:
                transitions.append([start, end])
    if template == "who-is-the-spy" and scene.get("intro"):
        # Spy positive-z characters/labels interleave with the z=auto intro.
        # A full composite preserves that original CSS stacking exactly.
        end = min(scene["episode"]["durationInFrames"], scene["intro"]["durationInFrames"])
        if end > 0:
            transitions.append([0, end])
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


def layer_frame_ranges(scene, layers, transitions=()):
    """Only skip unmounted/invisible components, never infer that motion is static."""
    total = scene["episode"]["durationInFrames"]
    intro_end = (scene.get("intro") or {}).get("durationInFrames", 0)
    spy = scene["episode"].get("template") == "who-is-the-spy"
    meme = scene["episode"].get("style", {}).get("caption_style", "ba") != "ba"
    result = {}
    for layer in layers:
        ranges = []
        if layer in {"background", "reference", "transition"}:
            ranges = [(0, total)]
        elif layer == "intro":
            ranges = [(0, intro_end)]
        else:
            for shot in scene["shots"]:
                start, end = shot["from"], shot["from"] + shot["durationInFrames"]
                ui_start = max(start, intro_end)
                entries = shot.get("characters", [])
                lines = shot.get("lines", [])
                choices = shot.get("choices") or {}
                if layer.startswith("character-slot:"):
                    if int(layer.split(":", 1)[1]) < len(entries):
                        ranges.append((start, end))
                elif layer.startswith("character:"):
                    if any(entry["id"] == layer.split(":", 1)[1] for entry in entries):
                        ranges.append((start, end))
                elif layer == "ui":
                    if not spy or not meme or shot.get("buttons"):
                        ranges.append((ui_start, end))
                    elif choices.get("options"):
                        begin = max(0, choices.get("fromFrame", 0))
                        select = max(begin, choices.get("selectFrame", begin + 30))
                        hide = max(select + 1, choices.get("hideFrame", select + 22))
                        ranges.append((max(ui_start, start + begin), min(end, start + hide)))
                elif layer == "chrome":
                    if not spy or not meme:
                        ranges.append((ui_start, end))
                elif layer == "buttons":
                    if shot.get("buttons"):
                        ranges.append((ui_start, end))
                elif layer == "choices":
                    if choices.get("options"):
                        begin = max(0, choices.get("fromFrame", 0))
                        select = max(begin, choices.get("selectFrame", begin + 30))
                        hide = max(select + 1, choices.get("hideFrame", select + 22))
                        ranges.append((max(ui_start, start + begin), min(end, start + hide)))
                elif layer in {"thought", "meme", "dialogue-ba"}:
                    if layer == "thought":
                        relevant = [line for line in lines if line.get("kind") == "thought"]
                    elif (layer == "meme") == meme:
                        relevant = [line for line in lines if line.get("kind") != "thought"]
                        if choices.get("prompt"):
                            ranges.append((ui_start, end))
                    else:
                        relevant = []
                    for line in relevant:
                        begin = start if layer == "thought" else ui_start
                        ranges.append((max(begin, line["from"]), min(end, line["from"] + line["durationInFrames"])))
                elif layer in {"dialogue", "dialogue-full"}:
                    if choices.get("prompt"):
                        ranges.append((ui_start, end))
                    for line in lines:
                        begin = start if spy and line.get("kind") == "thought" else ui_start
                        ranges.append((max(begin, line["from"]),
                                       min(end, line["from"] + line["durationInFrames"])))
                elif layer in {"labels", "word-labels", "votes"} and spy:
                    if layer != "votes":
                        for entry in entries:
                            if entry.get("label"):
                                motion_start = (entry.get("motion") or {}).get("startFrame")
                                ranges.append((start, min(end, start + motion_start) if motion_start is not None else end))
                    if layer != "word-labels" and shot.get("voteTags"):
                        tail = lines[-1]["from"] + lines[-1]["durationInFrames"] if lines else start
                        ranges.append((max(start, tail), end))
        merged = []
        for start, end in sorted((max(0, a), min(total, b)) for a, b in ranges):
            if end <= start:
                continue
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(end, merged[-1][1])
            else:
                merged.append([start, end])
        if layer not in {"reference", "transition"}:
            for a, b in transitions:
                remaining = []
                for start, end in merged:
                    if b <= start or a >= end:
                        remaining.append([start, end])
                    else:
                        if start < a:
                            remaining.append([start, a])
                        if b < end:
                            remaining.append([b, end])
                merged = remaining
        result[layer] = merged
    return result


def render_jobs(scene, layers, transitions=()):
    """Render every dynamic frame; reuse only analytically constant component states.

    ImageStage/GradientBackground have no frame hooks. Their only ShotView input
    varying with time is the radial speaker/focus state. StoryChrome has neither
    frame hooks nor shot props. Buttons/choices and all other layers remain full
    frame renders. A new animation in these components requires updating this
    contract and the pixel comparison regression.
    """
    ranges = layer_frame_ranges(scene, layers, transitions)
    spy = scene["episode"].get("template") == "who-is-the-spy"
    jobs = []
    boundaries = {0, scene["episode"]["durationInFrames"]}
    for shot in scene["shots"]:
        boundaries.update((shot["from"], shot["from"] + shot["durationInFrames"]))
        boundaries.add(shot["from"] + 30)
        for line in shot.get("lines", []):
            boundaries.update((line["from"], line["from"] + line["durationInFrames"]))
        for entry in shot.get("characters", []):
            for cue in entry.get("emotionCues") or []:
                boundaries.add(shot["from"] + cue.get("startFrame", 0))
    for layer in layers:
        for start, end in ranges[layer]:
            static_candidate = layer in {"background", "ui", "chrome"} or (not spy and layer.startswith("character"))
            points = sorted({start, end, *[f for f in boundaries if start < f < end]}) if static_candidate else [start, end]
            for a, b in zip(points, points[1:]):
                job = {"layer": layer, "start": a, "end": b}
                shots = [shot for shot in scene["shots"] if shot["from"] <= a < shot["from"] + shot["durationInFrames"]]
                if len(shots) == 1:
                    shot = shots[0]
                    if layer == "background":
                        lines = shot.get("lines", [])
                        active = next((line for line in lines if line["from"] <= a < line["from"] + line["durationInFrames"]), None)
                        display = active
                        if spy and display is None:
                            display = next((line for line in reversed(lines) if a >= line["from"]), lines[0] if lines else None)
                        entry = next((entry for entry in shot.get("characters", []) if display and entry["id"] == display["speaker"]), None)
                        focus = None
                        if spy and ((display and display.get("kind") == "thought") or not lines):
                            focus = next((entry for entry in shot.get("characters", []) if entry["id"] == shot.get("focus")), None)
                        state = {"scene": shot.get("scene"), "background": shot.get("background"),
                                 "camera": shot.get("camera"), "speakerX": (entry or {}).get("x", .5),
                                 "focus": bool(focus), "focusX": (focus or {}).get("x")}
                        job["staticKey"] = "background:" + json.dumps(state, sort_keys=True)
                    elif layer == "chrome" or (layer == "ui" and not shot.get("buttons") and not (shot.get("choices") or {}).get("options")):
                        job["staticKey"] = "story-chrome"
                    elif not spy and layer.startswith("character") and a >= shot["from"] + 30:
                        entries = shot.get("characters", [])
                        if layer.startswith("character-slot:"):
                            slot = int(layer.split(":", 1)[1])
                            entry = entries[slot] if slot < len(entries) else None
                        else:
                            entry = next((e for e in entries if e["id"] == layer.split(":", 1)[1]), None)
                        if entry and not any(entry.get(key) for key in ("actions", "bubbles", "motion", "turns")):
                            lines = shot.get("lines", [])
                            active = next((line for line in lines if line["from"] <= a < line["from"] + line["durationInFrames"]), None)
                            speaking = active and active["speaker"] == entry["id"]
                            held = next((line.get("emotion") for line in reversed(lines) if line["speaker"] == entry["id"] and a >= line["from"]), None) if entry.get("holdEmotion") else None
                            emotion = ((active.get("emotion") if speaking else held) or entry.get("emotion"))
                            cued = None
                            for cue in entry.get("emotionCues") or []:
                                if a >= shot["from"] + cue.get("startFrame", 0):
                                    cued = cue.get("emotion")
                            emotion = cued or emotion
                            state = {"entry": entry, "data": scene["characters"].get(entry["id"]),
                                     "emotion": emotion, "dimmed": bool(active) and not speaking}
                            job["staticKey"] = "character:" + json.dumps(state, sort_keys=True)
                if jobs and all(jobs[-1].get(key) == job.get(key) for key in ("layer", "staticKey")) and jobs[-1]["end"] == a:
                    jobs[-1]["end"] = b
                else:
                    jobs.append(job)
    jobs.extend({"layer": "transition", "start": a, "end": b} for a, b in transitions)
    return jobs


def effect_audio_events(scene):
    """Additional UI/bubble sounds; excludes existing voice, line-click and BGM.

    startFrame/endFrame bound playback; trimInFrames preserves source position
    when the intro or shot boundary hides the beginning of an effect.
    """
    events = []
    total = scene["episode"]["durationInFrames"]
    intro_end = (scene.get("intro") or {}).get("durationInFrames", 0)
    sounds = (scene.get("ui") or {}).get("sfx") or {}

    def add(src, start, end, volume, visible_start=0, label="effect"):
        a, b = max(0, start, visible_start), min(total, end)
        if src and b > a:
            events.append({"src": src, "startFrame": a, "endFrame": b,
                "trimInFrames": a - start, "volume": volume, "label": label})

    if scene.get("intro"):
        # Intro stays mounted even after fading out, matching production audio.
        add(sounds.get("click"), 22, 32, 0.3, label="intro click")
    for shot in scene["shots"]:
        base = shot["from"]
        end = min(total, base + shot["durationInFrames"])
        for character in shot.get("characters", []):
            for cue in character.get("bubbles", []):
                if cue.get("sound") is not False:
                    add(cue.get("audio"), base + cue["startFrame"], end, 0.5,
                        label=f"{character['id']} {cue['name']}")
        for button in shot.get("buttons", []):
            if button.get("pressFrame") is not None:
                start = base + max(0, round(button["pressFrame"]))
                add(sounds.get("click"), start, min(end, start + 12), 0.55,
                    max(base, intro_end), "button click")
        choice = shot.get("choices") or {}
        if choice.get("options"):
            start = max(0, choice.get("fromFrame", 0))
            select = max(start, choice.get("selectFrame", start + 30))
            hide = max(select + 1, choice.get("hideFrame", select + 22))
            visible_end = min(end, base + hide)
            add(sounds.get("hover"), base + start, min(visible_end, base + start + 10),
                0.28, max(base, intro_end), "choice hover")
            add(sounds.get("select"), base + select, min(visible_end, base + select + 12),
                0.65, max(base, intro_end), "choice select")
    return events
