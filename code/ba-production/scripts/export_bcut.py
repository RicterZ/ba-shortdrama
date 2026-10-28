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
from PIL import Image

from bcut_processor import load_processor

import lib


TEMPLATES = Path(__file__).with_name("bcut_templates")
TOKEN = "__BA_ASSETS__/"


def hex_rgb(value, fallback="#ffffff"):
    text = str(value or fallback).strip().lstrip("#")
    if len(text) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        text = fallback.lstrip("#")
    number = int(text, 16)
    return {"r": ((number >> 16) & 255) / 255, "g": ((number >> 8) & 255) / 255,
            "b": (number & 255) / 255, "a": 1}


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


def build(scene, raws, output, *, visual_layers=False, editable_captions=False, drop_voice=False):
    ep = scene["episode"]
    processor = load_processor(scene)
    width, height, fps = ep["width"], ep["height"], ep["fps"]
    if min(width, height, fps, ep["durationInFrames"]) <= 0:
        raise ValueError("Invalid canvas, frame rate or duration")
    # The static draft rounds each boundary on its own, the same way the
    # pre-generalization exporter did. Rendered layers keep the earlier floor
    # so a frame belongs to the clip that starts on it.
    ms = (lambda frame: math.floor(frame * 1000 / fps)) if visual_layers else (
        lambda frame: round(frame * 1000 / fps))
    end_ms = ms(ep["durationInFrames"])
    assets = output / "assets"
    assets.mkdir()
    draft = template("empty_draft")
    tl = draft["timelineWidget"]["timeline"]
    tl["config"].update(videoRes={"width": width, "height": height},
                        videoFps={"num": fps, "den": 1})
    tl["videoTracks"] = []
    registered = set()
    caption_lanes = {}
    if visual_layers:
        warnings = [
            "画面由制作模板逐帧分层渲染，保留动画、气泡、界面与字幕。背景、角色层和界面可以独立移动、裁剪。",
            "静态画面为 PNG，动画为无损透明 MOV，不是必剪原生关键帧；转场期间使用短暂的合成画面。",
            "正文为可编辑字幕，字形、换行和出字效果与原片存在差异。" if editable_captions else
            "字幕为原样渲染的图层；修改文字需修改脚本后重新导出。",
        ]
    else:
        warnings = [
            "背景和立绘是图片素材，文字是必剪原生字幕；淡入、滑入、走位、跳跃和缩放写成必剪关键帧。",
            "片头标题卡、对话框底板和界面按钮是模板渲染的图片；转身和动作预设写成关键帧；气泡、选项和按钮按下动画是透明 MOV，▼ 提示是循环 MOV。没有转场叠化。",
            "立绘按分镜位置做成透明底全画布图。说话时用该句表情，说完回到镜头常驻脸；他人说话时压暗。",
            *getattr(processor, "EXPORT_WARNINGS", ()),
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

    def image(name, start, end, index, label=None, keyframes=()):
        if end <= start:
            return
        clip = template("image_clip")
        # Legacy Windows crop effects without crop geometry become 0x0 crops
        # in macOS Bcut, producing infinities and a completely black preview.
        clip["fxs"] = [fx for fx in clip["fxs"] if fx.get("businessType") != 2]
        clip["propertyFxList"] = []
        if keyframes:
            transform = next(fx for fx in clip["fxs"]
                             if fx["fxName"] == "Transform 2D" and fx["businessType"] == 1)
            rotates = any(key.get("rotation") for key in keyframes)
            transform["keyFrameInfos"] = [
                item for key in keyframes for item in (
                    {"paramID": "Trans X", "timePosition": ms(key["frame"]) - start,
                     "transX": key["transX"], "transY": key["transY"]},
                    {"paramID": "Scale X", "timePosition": ms(key["frame"]) - start,
                     "scaleX": key.get("scaleX", key["scale"]), "scaleY": key["scale"]},
                    {"paramID": "Opacity", "timePosition": ms(key["frame"]) - start,
                     "opacity": key["opacity"]},
                    *([{"paramID": "Rotation", "timePosition": ms(key["frame"]) - start,
                        "rotation": key.get("rotation", 0)}] if rotates else []))]
            draft["timelineWidget"]["tracking"]["tracks"]["KeyFrame"] = True
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
            # Bcut scales the outline with the clip; outlineWidth stays in text units.
            clip["scaleX"] = clip["scaleY"] = scale
        if color is not None:
            clip["textColor"] = hex_rgb(color)
        if outline is not None:
            clip["outlineColor"] = hex_rgb(outline)
        if rotation is not None:
            clip["rotation"] = rotation
        clip["assetInfo"].update(content=text, displayName=text, duration=end-start)
        # A Bcut track shows one clip at a time; simultaneous text gets its own lane.
        lanes = caption_lanes.setdefault(index, [])
        lane = next((lane for lane in lanes if all(
            end <= other["inPoint"] or start >= other["outPoint"] for other in lane)), None)
        if lane is None:
            lane = []
            lanes.append(lane)
        lane.append(clip)
        return clip

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

    if visual_layers:
        from render_bcut_layers import render_layers
        # Replace static approximations with the same components used by the video.
        tl["videoTracks"] = []
        draft["mainWindow"]["browserPanelFiles"] = []
        registered.clear()
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
    else:
        if hasattr(processor, "images"):
            from image_layout import render_images
            spans = render_images(scene, raws, assets, processor.images(scene))
            layers = {}
            placed = []
            for span in spans:
                layers.setdefault(span["layer"], len(layers))
                placed.append((span, layers[span["layer"]]))
        else:
            spans = processor.static_spans(scene, assets, copied)
            placed = [(span, int(span["layer"])) for span in spans]
        for span, index in placed:
            image(span["name"], ms(span["startFrame"]), ms(span["endFrame"]),
                  index, span["label"], span.get("keyframes", ()))
        stills = processor.stills(scene) if hasattr(processor, "stills") else []
        if stills:
            from render_bcut_layers import render_layers
            from compact_bcut_layers import compact_layers, encode
            jobs = []
            for s in stills:
                if "frame" in s:
                    jobs.append({"layer": s["layer"], "start": s["frame"], "end": s["frame"] + 1})
                elif "loop" in s:
                    jobs.append({"layer": s["layer"], "start": 0, "end": s["loop"]})
                else:
                    jobs += [{"layer": s["layer"], "start": a, "end": b} for a, b in s["spans"]]
            rendered = render_layers(scene, raws, assets, jobs=jobs)
            top = max((index for _, index in placed), default=0) + 1
            for offset, layer in enumerate(dict.fromkeys(s["layer"] for s in stills)):
                index = top + offset
                own = sorted((span for span in rendered if span["layer"] == layer),
                             key=lambda span: span["startFrame"])
                for still in (s for s in stills if s["layer"] == layer):
                    if "animated" in still:
                        for span in compact_layers(own, scene, assets):
                            image(span["name"], ms(span["startFrame"]), ms(span["endFrame"]),
                                  index, still["label"])
                        continue
                    if "loop" in still:
                        if not own:
                            continue
                        cycle = still["loop"]
                        name = encode(own, layer, fps, assets)["name"]
                        for a, b in still["spans"]:
                            for c in range(a, b, cycle):
                                image(name, ms(c), ms(min(b, c + cycle)), index, still["label"])
                        continue
                    name = next((span["name"] for span in own
                                 if span["startFrame"] <= still["frame"] < span["endFrame"]), None)
                    if not name:
                        continue
                    for a, b in still["spans"]:
                        keys = [{"frame": f, "transX": 0, "transY": 0, "scale": 1, "opacity": o}
                                for f, o in still.get("fade", ()) if a <= f <= b]
                        image(name, ms(a), ms(b), index, still["label"], keys)
        if spans:
            with Image.open(assets / spans[0]["name"]) as cover_image:
                cover_image.convert("RGB").save(output / "cover.jpg", quality=85)
    from bcut_events import AudioEvent
    for event in processor.audio_events(scene, visual_layers=visual_layers):
        if not isinstance(event, AudioEvent):
            raise ValueError("Processors must return AudioEvent objects")
        # Track 0 is the dialogue/voice layer. Dropping it leaves the captions
        # and the rest of the timeline intact for an external voice pass.
        if drop_voice and event.track == 0:
            continue
        event.validate(ep["durationInFrames"])
        start_ms = ms(event.start)
        end_point = (min(end_ms, start_ms + ms(event.span_frames))
                     if event.span_frames else ms(event.end))
        audio(event.src, start_ms, end_point, event.track, event.volume,
              event.loop, ms(event.fade_in), ms(event.fade_out), trim_in=ms(event.trim_in))
    # Template processors supply pixel geometry; this writer knows only Bcut units.
    from text_layout import text_elements
    for element in text_elements(scene, visual_layers=visual_layers,
                                 editable_captions=editable_captions):
        if not element.text or ms(element.end) <= ms(element.start):
            continue
        scale = (round(0.56 * element.font_size / height / .042, 4)
                 if element.font_size is not None else None)
        clip = caption(element.text, ms(element.start), ms(element.end), element.track,
                x=round(2 * element.center_x / width - 1, 4) if element.center_x is not None else None,
                y=round(1 - 2 * element.center_y / height, 4) if element.center_y is not None else None,
                scale=scale, color=element.color, outline=element.outline, rotation=element.rotation)
        if element.alignment is not None:
            clip["textAlignment"] = element.alignment
        if element.draw_outline is not None:
            clip["drawOutline"] = element.draw_outline
    for index in sorted(caption_lanes):
        for lane in caption_lanes[index]:
            track("caption", len(tl["captionTracks"])).extend(lane)
    for key, clip_key in (("videoTracks", "clips"), ("audioTracks", "audioClips"), ("captionTracks", "captions")):
        kept = [item for item in tl[key] if item[clip_key]]
        for index, item in enumerate(kept):
            # Video and caption tracks share the visual stacking index. Giving
            # both index 0 places the subtitles underneath opaque backgrounds.
            item["index"] = index + (len(tl["videoTracks"]) if key == "captionTracks" else 0)
        tl[key] = kept
        for item in tl[key]:
            item[clip_key].sort(key=lambda clip: (clip["inPoint"], clip["outPoint"]))
    controls = getattr(processor, "TEXT_BELOW", set())
    if visual_layers and editable_captions and controls:
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
    clip_count = sum(len(t["clips"]) for t in tl["videoTracks"])
    draft["timelineWidget"]["tracking"]["tracks"].update(
        video_tracks=len(tl["videoTracks"]), audio_tracks=len(tl["audioTracks"]),
        video_count=clip_count if not visual_layers else sum(
            c.get("mediaType") == 0 for t in tl["videoTracks"] for c in t["clips"]),
        pic_count=clip_count if not visual_layers else sum(
            c.get("mediaType") == 1 for t in tl["videoTracks"] for c in t["clips"]),
        subtitles=";".join(c["uid"] for t in tl["captionTracks"] for c in t["captions"]))
    used = {clip["sourcePath"].removeprefix(TOKEN)
            for key, clips in (("videoTracks", "clips"), ("audioTracks", "audioClips"))
            for tr in tl[key] for clip in tr[clips]}
    for path in assets.iterdir():
        if path.is_file() and path.name not in used:
            path.unlink()
    lib.write_json(output / "draft.bjson", draft)
    manifest = {"name": ep["title"], "duration_ms": end_ms, "warnings": warnings, "format": "ba-bcut-1"}
    if visual_layers:
        manifest["visual_mode"] = "production-layers"
    lib.write_json(output / "manifest.json", manifest)
    shutil.copyfile(Path(__file__).with_name("install_bcut.py"), output / "install_bcut.py")
    shutil.copyfile(lib.ROOT / "licenses/dsh-bcut-edit-MIT.txt", output / "LICENSE-templates.txt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--mode", choices=("keyframes", "rendered"), default="keyframes",
                        help="keyframes: still images, native captions and Bcut keyframes; "
                             "rendered: frame-by-frame template layers")
    parser.add_argument("--captions", choices=("rendered", "editable"), default="rendered",
                        help="only for --mode rendered")
    parser.add_argument("--drop-voice", action="store_true",
                        help="skip the dialogue audio track, keeping captions and the timeline")
    args = parser.parse_args()
    episode = lib.resolve_episode(args.episode, lock=True)
    destination = episode / "output" / f"bcut-{uuid.uuid4().hex[:8]}"
    destination.parent.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=destination.parent))
    try:
        build(lib.load_json(episode / "project/scene.json"), episode / "raws", tmp,
              visual_layers=args.mode == "rendered", editable_captions=args.captions == "editable",
              drop_voice=args.drop_voice)
        tmp.rename(destination)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    print(f"Bcut bundle: {destination}")
    print("Close Bcut, then in that directory run: python install_bcut.py --bcut-closed")


if __name__ == "__main__":
    main()
