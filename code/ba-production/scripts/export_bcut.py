"""Export an experimental, portable Bcut 3.10.3 draft (no application writes)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
import uuid
from pathlib import Path

import av
from PIL import Image, ImageOps

import lib


TEMPLATES = Path(__file__).with_name("bcut_templates")
TOKEN = "__BA_ASSETS__/"


def visible_bounds(shots, index):
    """Hard-cut at the next shot. Transition overlap stays in scene.json for Remotion."""
    shot = shots[index]
    start = int(shot["from"])
    end = start + int(shot["durationInFrames"])
    if index + 1 < len(shots):
        end = min(end, int(shots[index + 1]["from"]))
    return start, max(start, end)


def emotion_at(entry, shot, frame):
    """Match the official renderer: a cue wins, then the spoken line, then a held face."""
    standing = entry.get("emotion") or "default"
    local = frame - int(shot["from"])
    cued = None
    for cue in entry.get("emotionCues") or []:
        if local >= int(cue.get("startFrame", 0)):
            cued = cue.get("emotion") or standing
    if cued:
        return cued
    for line in shot.get("lines") or []:
        if line.get("speaker") != entry["id"]:
            continue
        start = int(line["from"])
        if start <= frame < start + int(line["durationInFrames"]):
            return line.get("emotion") or standing
    if entry.get("holdEmotion"):
        held = None
        for line in shot.get("lines") or []:
            if line.get("speaker") == entry["id"] and frame >= int(line["from"]):
                held = line.get("emotion") or standing
        if held:
            return held
    return standing


def expression_spans(entry, shot, start, end):
    points = {start, end}
    for line in shot.get("lines") or []:
        if line.get("speaker") != entry["id"]:
            continue
        a = int(line["from"])
        b = a + int(line["durationInFrames"])
        if start < a < end:
            points.add(a)
        if start < b < end:
            points.add(b)
    for cue in entry.get("emotionCues") or []:
        at = int(shot["from"]) + int(cue.get("startFrame", 0))
        if start < at < end:
            points.add(at)
    ordered = sorted(points)
    spans = []
    for a, b in zip(ordered, ordered[1:]):
        emotion = emotion_at(entry, shot, a)
        if spans and spans[-1][2] == emotion:
            spans[-1] = (spans[-1][0], b, emotion)
        else:
            spans.append((a, b, emotion))
    return spans


def template(name):
    value = json.loads((TEMPLATES / f"{name}.json").read_text(encoding="utf-8"))

    def fresh(obj):
        if isinstance(obj, dict):
            return {k: str(uuid.uuid4().int)[:19] if k in {"idString", "uid"}
                    else fresh(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [fresh(v) for v in obj]
        return obj

    return fresh(value)


def build(scene, raws, output):
    ep = scene["episode"]
    if ep.get("template", "official") not in {"official", "blue-archive"}:
        raise ValueError("Only the official template is supported; spy UI cannot be translated.")
    width, height, fps = ep["width"], ep["height"], ep["fps"]
    if min(width, height, fps, ep["durationInFrames"]) <= 0:
        raise ValueError("Invalid canvas, frame rate or duration")
    ms = lambda frame: round(frame * 1000 / fps)
    end_ms = ms(ep["durationInFrames"])
    assets = output / "assets"
    assets.mkdir()
    draft = template("empty_draft")
    tl = draft["timelineWidget"]["timeline"]
    tl["config"].update(videoRes={"width": width, "height": height},
                        videoFps={"num": fps, "den": 1})
    tl["videoTracks"] = []
    registered = set()
    warnings = [
        "必剪 3.10.3 明文草稿。本机没有安装必剪，还没有在应用里打开验证。",
        "可编辑的静态分层，不是成片逐帧复刻：没有镜头运动、转场叠化、入场、走位、转身、气泡、压暗和界面按钮。片头只导出标题。",
        "立绘按分镜位置烘焙成透明底全画布图。说话时用该句表情，说完回到镜头常驻脸；holdEmotion 和 emotionCues 会保留。",
    ]

    def source(relative):
        path = (raws / relative).resolve()
        if not path.is_relative_to(raws.resolve()) or not path.is_file():
            raise ValueError(f"Missing or unsafe episode asset: {relative}")
        return path

    def copied(relative):
        path = source(relative)
        name = hashlib.sha256(path.read_bytes()).hexdigest()[:20] + path.suffix.lower()
        if not (assets / name).exists():
            shutil.copyfile(path, assets / name)
        return name

    def track(kind, index):
        key, clips, typ = {"video": ("videoTracks", "clips", 1),
                           "audio": ("audioTracks", "audioClips", 2),
                           "caption": ("captionTracks", "captions", 4)}[kind]
        while len(tl[key]) <= index:
            item = {clips: [], "compacted": False, "index": len(tl[key]),
                    "idString": str(uuid.uuid4().int)[:19], "trackType": typ}
            if kind == "video":
                item.update(transitions=[], mute=False, split=False)
            if kind == "audio":
                item["audioTrackType"] = 100
            tl[key].append(item)
        return tl[key][index][clips]

    def image(name, start, end, index, label=None):
        if end <= start:
            return
        clip = template("image_clip")
        path = TOKEN + name
        label = label or name
        clip.update(inPoint=start, outPoint=end, trimIn=0, trimOut=end-start,
                    sourcePath=path, originalFilePath=path)
        with Image.open(assets / name) as im:
            w, h = im.size
        clip["assetInfo"].update(srcPath=path, width=w, height=h,
                                  displayName=label, itemName=name, content=label)
        track("video", index).append(clip)
        if path not in registered:
            item = template("browser_file_image")
            item.update(srcPath=path, width=w, height=h, duration="0")
            draft["mainWindow"]["browserPanelFiles"].append(item)
            registered.add(path)

    def caption(text, start, end):
        if not text or end <= start:
            return
        clip = template("caption")
        clip.update(captionText=text, inPoint=start, outPoint=end)
        for key in ("defaultFontPath", "fontPackagePath"):
            clip[key] = ""
        clip["assetInfo"].update(content=text, displayName=text, duration=end-start,
                                  fontSrcPath="")
        track("caption", 0).append(clip)

    def audio(relative, start, end, index, volume=1, loop=False, fade_in=0, fade_out=0):
        if not math.isfinite(volume) or volume < 0:
            raise ValueError("Invalid audio volume")
        name = copied(relative)
        with av.open(str(assets / name)) as container:
            stream = container.streams.audio[0]
            duration = (float(stream.duration * stream.time_base) if stream.duration is not None
                        else float(container.duration or 0) / av.time_base)
        total = round(duration * 1000)
        if total <= 0:
            raise ValueError(f"Unknown audio duration: {relative}")
        first = start
        while start < end:
            span = min(total, end - start)
            clip = template("audio_clip")
            path = TOKEN + name
            clip.update(inPoint=start, outPoint=start+span, trimIn=0, trimOut=span,
                        sourcePath=path, originalFilePath=path, materialId="", markSet=[],
                        fadeIn=min(fade_in, span) if start == first else 0,
                        fadeOut=min(fade_out, span) if start+span == end else 0)
            clip["assetInfo"].update(srcPath=path, duration=total, displayName=name,
                                      itemName=name, content="", realMaterialId="", customInfos={})
            clip["fxs"][0]["gainValue"] = 20 * math.log10(volume) if volume else -120
            track("audio", index).append(clip)
            start += span
            if not loop:
                break

    characters = list(scene.get("characters", {}))
    shots = scene["shots"]
    for index, shot in enumerate(shots):
        start_frame, end_frame = visible_bounds(shots, index)
        start, end = ms(start_frame), ms(end_frame)
        bg = shot.get("scene", {}).get("image")
        if not bg:
            raise ValueError(f"Shot {shot['id']} has no snapshot background image")
        name = copied(bg)
        with Image.open(assets / name) as im:
            bg_name = f"background-{uuid.uuid4().hex}.png"
            fitted = ImageOps.fit(im.convert("RGB"), (width, height))
            fitted.save(assets / bg_name)
            if not (output / "cover.jpg").exists():
                fitted.save(output / "cover.jpg", quality=85)
        image(bg_name, start, end, 0, shot["id"])
        for entry in shot.get("characters", []):
            char = scene["characters"][entry["id"]]
            outfit_id = entry.get("outfit") or char["default_outfit"]
            sprites = char["outfits"][outfit_id]["sprites"]
            track_index = characters.index(entry["id"]) + 1
            for a, b, emotion in expression_spans(entry, shot, start_frame, end_frame):
                original = sprites.get(emotion) or sprites.get("default")
                if not original:
                    raise ValueError(f"{entry['id']}/{outfit_id} has no sprite for {emotion}")
                original_name = copied(original)
                with Image.open(assets / original_name) as im:
                    im = im.convert("RGBA")
                    scale = entry.get("scale", 1)
                    h = max(1, round(height * entry.get("height", 1.08) * scale))
                    w = max(1, round(im.width * h / im.height))
                    im = im.resize((w, h), Image.Resampling.LANCZOS)
                    if entry.get("facing") == "left":
                        im = ImageOps.mirror(im)
                    canvas = Image.new("RGBA", (width, height))
                    # CSS scales about the center of the original (unscaled) box.
                    box_h = height * entry.get("height", 1.08)
                    cy = height * (1 - entry.get("bottom", -0.25)) - box_h / 2
                    canvas.paste(im, (round(width * entry.get("x", .5) - w / 2), round(cy - h / 2)))
                    name = f"pose-{uuid.uuid4().hex}.png"
                    canvas.save(assets / name)
                image(name, ms(a), ms(b), track_index, f"{entry['id']} {emotion}")
        for line in shot["lines"]:
            a, b = ms(line["from"]), ms(line["from"] + line["durationInFrames"])
            caption(line["text"], a, b)
            if line.get("audio"):
                audio(line["audio"], a, b, 0)
            ui = scene.get("ui", {})
            click = ui.get("sfx", {}).get("click")
            if click and ui.get("lineClick", True) and a >= ms((scene.get("intro") or {}).get("durationInFrames", 0)):
                audio(click, a, min(end_ms, a + ms(10)), 2, ui.get("lineClickVolume", .14))
    intro = scene.get("intro") or {}
    caption(intro.get("title"), 0, ms(intro.get("durationInFrames", 0)))
    bgm = scene.get("bgm")
    if bgm:
        audio(bgm["src"], 0, end_ms, 1, bgm.get("volume", .15), bgm.get("loop", True),
              ms(bgm.get("fadeInFrames", 45)), ms(bgm.get("fadeOutFrames", 75)))
    for key, clips in (("videoTracks", "clips"), ("audioTracks", "audioClips"), ("captionTracks", "captions")):
        for item in tl[key]:
            item[clips].sort(key=lambda clip: (clip["inPoint"], clip["outPoint"]))
    draft["timelineWidget"]["tracking"]["tracks"].update(
        video_tracks=len(tl["videoTracks"]), audio_tracks=len(tl["audioTracks"]),
        video_count=sum(len(t["clips"]) for t in tl["videoTracks"]),
        pic_count=sum(len(t["clips"]) for t in tl["videoTracks"]),
        subtitles=";".join(c["uid"] for t in tl["captionTracks"] for c in t["captions"]))
    lib.write_json(output / "draft.bjson", draft)
    lib.write_json(output / "manifest.json", {"name": ep["title"], "duration_ms": end_ms,
                                               "warnings": warnings, "format": "ba-bcut-1"})
    shutil.copyfile(Path(__file__).with_name("install_bcut.py"), output / "install_bcut.py")
    shutil.copyfile(lib.ROOT / "licenses/dsh-bcut-edit-MIT.txt", output / "LICENSE-templates.txt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True)
    args = parser.parse_args()
    episode = lib.resolve_episode(args.episode)
    destination = episode / "output" / f"bcut-{uuid.uuid4().hex[:8]}"
    destination.parent.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=destination.parent))
    try:
        build(lib.load_json(episode / "project/scene.json"), episode / "raws", tmp)
        tmp.rename(destination)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    print(f"Bcut bundle: {destination}")
    print("Close Bcut, then in that directory run: python install_bcut.py --bcut-closed")


if __name__ == "__main__":
    main()
