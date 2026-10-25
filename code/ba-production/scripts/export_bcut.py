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
from PIL import Image, ImageEnhance, ImageOps

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


def hex_rgb(value, fallback="#ffffff"):
    text = str(value or fallback).strip().lstrip("#")
    if len(text) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        text = fallback.lstrip("#")
    number = int(text, 16)
    return {"r": ((number >> 16) & 255) / 255, "g": ((number >> 8) & 255) / 255,
            "b": (number & 255) / 255, "a": 1}


def caption_scale(size_frac):
    """Map a frame-height fraction onto the draft template's subtitle scale."""
    return round(0.56 * (size_frac / 0.042), 4)


def caption_x(value):
    clamped = min(0.92, max(0.08, float(value)))
    return round((clamped - 0.5) * 2, 4)


def caption_y_top(top_frac, size_frac):
    center = top_frac + size_frac * 1.12 / 2
    return round(1 - 2 * center, 4)


def caption_y_bottom(bottom_frac, size_frac):
    center = 1 - bottom_frac - size_frac * 1.12 / 2
    return round(1 - 2 * center, 4)


def meme_size(text, base, width_frac):
    return min(base, width_frac / (max(1, len(text)) * 1.02))


def shot_focus(shot):
    """Spotlight holds for a thought shot or a silent reaction, not during speech."""
    focus = shot.get("focus")
    if not focus:
        return None
    lines = shot.get("lines") or []
    if any(line.get("kind", "speech") != "thought" for line in lines):
        return None
    return focus


def audible_spans(start, end, mutes):
    cursor = start
    spans = []
    for mute in sorted(mutes or [], key=lambda item: int(item["from"])):
        mute_start = int(mute["from"])
        mute_end = mute_start + int(mute["durationInFrames"])
        if mute_end <= cursor or mute_start >= end:
            continue
        if mute_start > cursor:
            spans.append((cursor, min(mute_start, end)))
        cursor = max(cursor, min(mute_end, end))
    if cursor < end:
        spans.append((cursor, end))
    return spans


def tone(image, brightness=None, color=None):
    if color is not None:
        image = ImageEnhance.Color(image).enhance(color)
    if brightness is not None:
        image = ImageEnhance.Brightness(image).enhance(brightness)
    return image


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


def build(scene, raws, output, *, visual_layers=False, editable_captions=False):
    ep = scene["episode"]
    template_id = ep.get("template", "official")
    if template_id not in {"official", "who-is-the-spy"}:
        raise ValueError("Only the official and who-is-the-spy templates are supported.")
    spy = template_id == "who-is-the-spy"
    width, height, fps = ep["width"], ep["height"], ep["fps"]
    if min(width, height, fps, ep["durationInFrames"]) <= 0:
        raise ValueError("Invalid canvas, frame rate or duration")
    # Bcut samples at exact frame times. Rounding a boundary upward keeps the
    # previous clip visible for one extra frame (e.g. frame 1424 at 30 fps).
    ms = lambda frame: math.floor(frame * 1000 / fps)
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
        "可编辑的静态分层，不是成片逐帧复刻：没有镜头运动、转场叠化、入场、走位、转身、气泡和界面按钮。片头只导出标题。",
        "立绘按分镜位置烘焙成透明底全画布图。说话时用该句表情，说完回到镜头常驻脸；holdEmotion 和 emotionCues 会保留。",
    ]
    if spy:
        warnings.append(
            "谁是卧底的词牌、大字幕、心理字幕和投票字按画面位置写成字幕。描边是必剪的单层描边。"
            "聚光灯只压暗背景和其他角色，没有径向光。"
        )
    if visual_layers:
        warnings = [
            "画面由制作模板逐帧分层渲染，保留动画、气泡、界面与字幕。背景、角色层和界面可以独立移动、裁剪。",
            "静态画面为 PNG，动画为无损透明 MOV，不是必剪原生关键帧；转场期间使用短暂的合成画面。",
            "正文为可编辑字幕，字形、换行和出字效果与原片存在差异。" if editable_captions else
            "字幕为原样渲染的图层；修改文字需修改脚本后重新导出。",
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
        # Legacy Windows crop effects without crop geometry become 0x0 crops
        # in macOS Bcut, producing infinities and a completely black preview.
        clip["fxs"] = [fx for fx in clip["fxs"] if fx.get("businessType") != 2]
        clip["propertyFxList"] = []
        path = TOKEN + name
        label = label or name
        clip.update(inPoint=start, outPoint=end, trimIn=0, trimOut=end-start,
                    sourcePath=path, originalFilePath=path)
        video = name.endswith(".mov")
        if video:
            w, h = width, height
            clip["mediaType"] = 0
            clip["assetInfo"].update(assetItemType=4, type=1, videoType=1,
                                     frameRateNum=fps, frameRateDen=1, duration=end-start)
        else:
            with Image.open(assets / name) as im:
                w, h = im.size
        clip["assetInfo"].update(srcPath=path, width=w, height=h,
                                  displayName=label, itemName=name, content=label)
        track("video", index).append(clip)
        if path not in registered:
            item = template("browser_file_image")
            item.update(srcPath=path, width=w, height=h, duration="0")
            if video:
                item.update(itemType=4, frameRateNum=fps, frameRateDen=1, duration=str(end-start))
            draft["mainWindow"]["browserPanelFiles"].append(item)
            registered.add(path)

    def caption(text, start, end, index=0, x=None, y=None, scale=None,
                color=None, outline=None, rotation=None):
        if not text or end <= start:
            return
        clip = template("caption")
        clip.update(captionText=text, inPoint=start, outPoint=end)
        if x is not None:
            clip["transX"] = x
        if y is not None:
            clip["transY"] = y
        if scale is not None:
            clip["scaleX"] = clip["scaleY"] = scale
            clip["outlineWidth"] = 12.5 * scale / 0.56
        if color is not None:
            clip["textColor"] = hex_rgb(color)
        if outline is not None:
            clip["outlineColor"] = hex_rgb(outline)
        if rotation is not None:
            clip["rotation"] = rotation
        clip["assetInfo"].update(content=text, displayName=text, duration=end-start)
        track("caption", index).append(clip)

    def native_dialogue(text, start, end):
        lines = text.splitlines() or [text]
        advance = max(sum(1 if ord(c) > 255 else .55 for c in row) for row in lines)
        text_width = advance * height * .038
        caption(text, ms(start), ms(end),
                x=2 * (.09 + text_width / width / 2 - .5),
                y=caption_y_top(.76, .038 * len(lines)), scale=.4256)
        if end > start and text:
            item = tl["captionTracks"][0]["captions"][-1]
            item.update(drawOutline=False, textAlignment=0)

    def audio(relative, start, end, index, volume=1, loop=False, fade_in=0, fade_out=0, trim_in=0):
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
        if loop:
            trim_in %= total
        first = start
        while start < end:
            span = min(total - trim_in, end - start)
            if span <= 0:
                break
            clip = template("audio_clip")
            path = TOKEN + name
            clip.update(inPoint=start, outPoint=start+span, trimIn=trim_in, trimOut=trim_in+span,
                        sourcePath=path, originalFilePath=path, materialId="", markSet=[],
                        fadeIn=min(fade_in, span) if start == first else 0,
                        fadeOut=min(fade_out, span) if start+span == end else 0)
            clip["assetInfo"].update(srcPath=path, duration=total, displayName=name,
                                      itemName=name, content="", realMaterialId="", customInfos={})
            clip["fxs"][0]["gainValue"] = 20 * math.log10(volume) if volume else -120
            track("audio", index).append(clip)
            start += span
            trim_in = 0
            if not loop:
                break

    characters = list(scene.get("characters", {}))
    shots = scene["shots"]
    for index, shot in enumerate(shots):
        start_frame, end_frame = visible_bounds(shots, index)
        start, end = ms(start_frame), ms(end_frame)
        bg = shot.get("scene", {}).get("image")
        if not bg and not visual_layers:
            raise ValueError(f"Shot {shot['id']} has no snapshot background image")
        if bg:
            name = copied(bg)
        else:
            name = f"cover-placeholder-{uuid.uuid4().hex}.png"
            Image.new("RGB", (width, height), "#101820").save(assets / name)
        focus = shot_focus(shot) if spy else None
        with Image.open(assets / name) as im:
            bg_name = f"background-{uuid.uuid4().hex}.png"
            fitted = ImageOps.fit(im.convert("RGB"), (width, height))
            if focus:
                fitted = tone(fitted, brightness=0.46, color=0.72)
            fitted.save(assets / bg_name)
            if not (output / "cover.jpg").exists():
                fitted.convert("RGB").save(output / "cover.jpg", quality=85)
        image(bg_name, start, end, 0, shot["id"])
        for entry in shot.get("characters", []):
            char = scene["characters"][entry["id"]]
            outfit_id = entry.get("outfit") or char["default_outfit"]
            sprites = char["outfits"][outfit_id]["sprites"]
            track_index = characters.index(entry["id"]) + 1
            for a, b, emotion in expression_spans(entry, shot, start_frame, end_frame):
                original = sprites.get(emotion) or sprites.get("default")
                if not original and visual_layers:
                    continue
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
                    if focus and entry["id"] != focus:
                        im = tone(im, brightness=0.38, color=0.28)
                    canvas = Image.new("RGBA", (width, height))
                    # CSS scales about the center of the original (unscaled) box.
                    box_h = height * entry.get("height", 1.08)
                    cy = height * (1 - entry.get("bottom", -0.25)) - box_h / 2
                    canvas.paste(im, (round(width * entry.get("x", .5) - w / 2), round(cy - h / 2)))
                    name = f"pose-{uuid.uuid4().hex}.png"
                    canvas.save(assets / name)
                image(name, ms(a), ms(b), track_index, f"{entry['id']} {emotion}")
            if not spy:
                continue
            label = entry.get("label") or {}
            if not label.get("text"):
                continue
            label_end = end_frame
            motion = entry.get("motion") or {}
            if motion.get("startFrame") is not None:
                label_end = min(label_end, int(shot["from"]) + int(motion["startFrame"]))
            secret = label.get("tone") == "secret"
            size = 0.058
            caption(label["text"], ms(start_frame), ms(label_end), 1,
                    x=caption_x(entry.get("x", 0.5)), y=caption_y_top(0.018, size),
                    scale=caption_scale(size), rotation=label.get("rotate", -3),
                    color="#ff9ab7" if secret else "#a9dcff",
                    outline="#ff5f8f" if secret else "#123a5a")
        if spy and shot.get("systemVoice"):
            audio(shot["systemVoice"], start,
                  min(end_ms, ms(shot["from"] + shot["durationInFrames"])), 3)
        lines = shot.get("lines") or []
        for line in lines:
            a, b = ms(line["from"]), ms(line["from"] + line["durationInFrames"])
            shown = line["text"].replace("。", "") if spy else line["text"]
            if spy and line.get("kind") == "thought":
                size = meme_size(shown, 0.048, 0.7)
                caption(shown, a, b, y=caption_y_bottom(0.17, size), scale=caption_scale(size),
                        color="#ffffff", outline="#0b1119", rotation=-1)
            elif spy and (not visual_layers or ep.get("style", {}).get("caption_style", "ba") == "meme"):
                size = meme_size(shown, 0.098, 0.84)
                color = scene["characters"].get(line["speaker"], {}).get("color", "#ffffff")
                caption(shown, a, b, y=caption_y_bottom(0.06, size), scale=caption_scale(size),
                        color=color, outline=color, rotation=-1.2)
            else:
                if visual_layers and editable_captions:
                    native_dialogue(shown, max(line["from"], (scene.get("intro") or {}).get("durationInFrames", 0)),
                                    line["from"] + line["durationInFrames"])
                else:
                    caption(shown, a, b)
            if line.get("audio"):
                audio(line["audio"], a, b, 0)
            ui = scene.get("ui", {})
            click = ui.get("sfx", {}).get("click")
            thought = spy and line.get("kind") == "thought"
            if click and not thought and ui.get("lineClick", True) and a >= ms((scene.get("intro") or {}).get("durationInFrames", 0)):
                audio(click, a, min(end_ms, a + ms(10)), 2, ui.get("lineClickVolume", .14))
        if spy and shot.get("voteTags"):
            vote_from = max(line["from"] + line["durationInFrames"] for line in lines) if lines else start_frame
            vote_from = max(start_frame, vote_from)
            for tag in shot["voteTags"]:
                speaker = next((entry for entry in shot.get("characters", [])
                                if entry["id"] == tag.get("speaker")), None)
                if not speaker or not tag.get("text") or vote_from >= end_frame:
                    continue
                size = 0.05
                caption(tag["text"], ms(vote_from), ms(end_frame), 2,
                        x=caption_x(speaker.get("x", 0.5)), y=caption_y_top(0.62, size),
                        scale=caption_scale(size), rotation=-2,
                        color=scene["characters"].get(tag["speaker"], {}).get("color", "#ffffff"),
                        outline="#08111f")
    intro = scene.get("intro") or {}
    if not visual_layers:
        caption(intro.get("title"), 0, ms(intro.get("durationInFrames", 0)))
    if visual_layers:
        from render_bcut_layers import render_layers, effect_audio_events
        # Replace static approximations with the same components used by the video.
        tl["videoTracks"] = []
        draft["mainWindow"]["browserPanelFiles"] = []
        registered.clear()
        if not (editable_captions and spy):
            tl["captionTracks"] = []
        spans = render_layers(scene, raws, assets, editable_captions=editable_captions)
        cover = Image.new("RGBA", (width, height))
        for span in spans:
            if span["startFrame"] <= 0 < span["endFrame"]:
                with Image.open(assets / span["name"]) as layer:
                    cover = Image.alpha_composite(cover, layer.convert("RGBA"))
        cover.convert("RGB").save(output / "cover.jpg", quality=90)
        from compact_bcut_layers import compact_layers
        spans = compact_layers(spans, scene, assets)
        # Bcut ripples gaps closed on video track 0 when opening a draft.
        # Intro/transition patches deliberately leave gaps in the other layers,
        # so reserve the main track for a continuous canvas underneath them.
        canvas_name = "timeline-canvas.png"
        Image.new("RGB", (width, height), "black").save(assets / canvas_name)
        image(canvas_name, 0, end_ms, 0, "连续画布（保持时间轴）")
        layer_indices = {}
        for span in spans:
            layer = span["layer"]
            if layer not in layer_indices:
                layer_indices[layer] = len(layer_indices) + 1
            image(span["name"], ms(span["startFrame"]), ms(span["endFrame"]),
                  layer_indices[layer], span["label"])
        for index, event in enumerate(effect_audio_events(scene)):
            audio(event["src"], ms(event["startFrame"]), ms(event["endFrame"]),
                  5 + index, event["volume"], trim_in=ms(event["trimInFrames"]))
        if editable_captions:
            for shot in shots:
                for line in ([] if spy else shot.get("lines", [])):
                    start = max(line["from"], intro.get("durationInFrames", 0))
                    end = min(line["from"] + line["durationInFrames"],
                              shot["from"] + shot["durationInFrames"])
                    # Bcut's transform positions the text box by its center.
                    # Approximate CJK advance to retain the production left edge.
                    native_dialogue(line["text"], start, end)
                prompt = (shot.get("choices") or {}).get("prompt")
                if prompt:
                    start = max(shot["from"], intro.get("durationInFrames", 0))
                    end = shot["from"] + shot["durationInFrames"]
                    occupied = [{"from": line["from"], "durationInFrames": line["durationInFrames"]}
                                for line in shot.get("lines", [])]
                    for a, b in audible_spans(start, end, occupied):
                        if spy and ep.get("style", {}).get("caption_style", "ba") == "meme":
                            text = prompt.replace("。", "")
                            size = meme_size(text, .098, .84)
                            speaker = (shot.get("lines") or [{}])[-1].get("speaker")
                            color = scene["characters"].get(speaker, {}).get("color", "#ffffff")
                            caption(text, ms(a), ms(b), y=caption_y_bottom(.06, size),
                                    scale=caption_scale(size), color=color, outline=color, rotation=-1.2)
                        else:
                            native_dialogue(prompt, a, b)
    bgm = scene.get("bgm")
    if bgm:
        mutes = bgm.get("muteRanges") if spy else None
        resume = int(bgm.get("resumeFadeFrames", 0)) if spy else 0
        for span_start, span_end in audible_spans(0, ep["durationInFrames"], mutes):
            fade_in = bgm.get("fadeInFrames", 45) if span_start == 0 else resume
            fade_out = bgm.get("fadeOutFrames", 75) if span_end == ep["durationInFrames"] else 0
            audio(bgm["src"], ms(span_start), ms(span_end), 1, bgm.get("volume", .15),
                  bgm.get("loop", True), ms(fade_in), ms(fade_out), trim_in=ms(span_start))
        if spy:
            for cue in bgm.get("cues") or []:
                audio(cue["src"], ms(cue["from"]), ms(cue["from"] + cue["durationInFrames"]),
                      4, cue.get("volume", 0.5), cue.get("loop", True))
    for key, clip_key in (("videoTracks", "clips"), ("audioTracks", "audioClips"), ("captionTracks", "captions")):
        kept = [item for item in tl[key] if item[clip_key]]
        for index, item in enumerate(kept):
            # Video and caption tracks share the visual stacking index. Giving
            # both index 0 places the subtitles underneath opaque backgrounds.
            item["index"] = index + (len(tl["videoTracks"]) if key == "captionTracks" else 0)
        tl[key] = kept
        for item in tl[key]:
            item[clip_key].sort(key=lambda clip: (clip["inPoint"], clip["outPoint"]))
    if visual_layers and editable_captions and not spy:
        controls = {"ui", "choices", "buttons", "chrome", "click", "intro"}
        # Composite transition clips omit native text and must remain below it.
        tl["videoTracks"].sort(key=lambda tr: (
            tr["clips"][0]["assetInfo"]["displayName"] in controls, tr["index"]))
        for index, tr in enumerate(tl["videoTracks"]):
            tr["index"] = index
        insertion = next((tr["index"] for tr in tl["videoTracks"]
                          if tr["clips"][0]["assetInfo"]["displayName"] in controls), len(tl["videoTracks"]))
        for tr in tl["videoTracks"]:
            if tr["index"] >= insertion:
                tr["index"] += len(tl["captionTracks"])
        for offset, tr in enumerate(tl["captionTracks"]):
            tr["index"] = insertion + offset
    draft["timelineWidget"]["tracking"]["tracks"].update(
        video_tracks=len(tl["videoTracks"]), audio_tracks=len(tl["audioTracks"]),
        video_count=sum(c.get("mediaType") == 0 for t in tl["videoTracks"] for c in t["clips"]),
        pic_count=sum(c.get("mediaType") == 1 for t in tl["videoTracks"] for c in t["clips"]),
        subtitles=";".join(c["uid"] for t in tl["captionTracks"] for c in t["captions"]))
    if visual_layers:
        used = {clip["sourcePath"].removeprefix(TOKEN)
                for key, clips in (("videoTracks", "clips"), ("audioTracks", "audioClips"))
                for tr in tl[key] for clip in tr[clips]}
        for path in assets.iterdir():
            if path.name not in used:
                path.unlink()
    lib.write_json(output / "draft.bjson", draft)
    lib.write_json(output / "manifest.json", {"name": ep["title"], "duration_ms": end_ms,
                                               "visual_mode": "production-layers" if visual_layers else "static",
                                               "warnings": warnings, "format": "ba-bcut-1"})
    shutil.copyfile(Path(__file__).with_name("install_bcut.py"), output / "install_bcut.py")
    shutil.copyfile(lib.ROOT / "licenses/dsh-bcut-edit-MIT.txt", output / "LICENSE-templates.txt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--captions", choices=("rendered", "editable"), default="rendered")
    args = parser.parse_args()
    episode = lib.resolve_episode(args.episode, lock=True)
    destination = episode / "output" / f"bcut-{uuid.uuid4().hex[:8]}"
    destination.parent.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=destination.parent))
    try:
        build(lib.load_json(episode / "project/scene.json"), episode / "raws", tmp,
              visual_layers=True, editable_captions=args.captions == "editable")
        tmp.rename(destination)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    print(f"Bcut bundle: {destination}")
    print("Close Bcut, then in that directory run: python install_bcut.py --bcut-closed")


if __name__ == "__main__":
    main()
