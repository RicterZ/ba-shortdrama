"""BA scene interpretation and static preview; Bcut writes only generic events."""
import uuid
from PIL import Image, ImageEnhance, ImageOps
from ba_layer_schedule import effect_audio_events


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


def static_spans(scene, assets, copied, *, spy=False):
    width, height = scene["episode"]["width"], scene["episode"]["height"]
    spans = []
    def image(name, start, end, index, label):
        if end > start:
            spans.append({"name": name, "startFrame": start, "endFrame": end,
                          "layer": str(index), "label": label})
    characters = list(scene.get("characters", {}))
    shots = scene["shots"]
    for index, shot in enumerate(shots):
        start_frame, end_frame = visible_bounds(shots, index)
        start, end = start_frame, end_frame
        bg = shot.get("scene", {}).get("image")
        if not bg:
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
                    if focus and entry["id"] != focus:
                        im = tone(im, brightness=0.38, color=0.28)
                    canvas = Image.new("RGBA", (width, height))
                    # CSS scales about the center of the original (unscaled) box.
                    box_h = height * entry.get("height", 1.08)
                    cy = height * (1 - entry.get("bottom", -0.25)) - box_h / 2
                    canvas.paste(im, (round(width * entry.get("x", .5) - w / 2), round(cy - h / 2)))
                    name = f"pose-{uuid.uuid4().hex}.png"
                    canvas.save(assets / name)
                image(name, a, b, track_index, f"{entry['id']} {emotion}")
    return spans


def composites(scene, *, spy=False):
    total = scene["episode"]["durationInFrames"]
    spans = []
    for shot in scene["shots"][1:]:
        transition = shot.get("transition") or {}
        if transition and transition.get("type") != "none":
            spans.append([int(shot["from"]), min(total, int(shot["from"]) + int(transition["durationInFrames"]))])
    if spy and scene.get("intro"):
        spans.append([0, min(total, scene["intro"]["durationInFrames"])])
    return [(a, b) for a, b in spans if b > a]


def audio_events(scene, *, visual_layers=False, spy=False):
    from bcut_events import AudioEvent
    total = scene["episode"]["durationInFrames"]
    intro_end = (scene.get("intro") or {}).get("durationInFrames", 0)
    ui = scene.get("ui") or {}
    shots = scene["shots"]
    for index, shot in enumerate(shots):
        visible_start, visible_end = visible_bounds(shots, index)
        # System voice covers the shot, including the transition overlap the
        # picture hard-cuts away. visible_start is still the shot start.
        shot_end = min(total, int(shot["from"]) + int(shot["durationInFrames"]))
        if spy and shot.get("systemVoice") and shot_end > visible_start:
            yield AudioEvent(shot["systemVoice"], visible_start, shot_end, track=3)
        for line in shot.get("lines") or []:
            start, end = line["from"], min(total, line["from"] + line["durationInFrames"])
            if line.get("audio") and end > start:
                yield AudioEvent(line["audio"], start, end)
            click = (ui.get("sfx") or {}).get("click")
            if (click and not (spy and line.get("kind") == "thought") and ui.get("lineClick", True)
                    and start >= intro_end and start < total):
                yield AudioEvent(click, start, min(total, start + 10), track=2,
                                 volume=ui.get("lineClickVolume", .14), span_frames=10)
    if visual_layers:
        for index, event in enumerate(effect_audio_events(scene)):
            yield AudioEvent(event["src"], event["startFrame"], event["endFrame"],
                track=5 + index, volume=event["volume"], trim_in=event["trimInFrames"])
    bgm = scene.get("bgm")
    if bgm:
        mutes = bgm.get("muteRanges") if spy else None
        resume = int(bgm.get("resumeFadeFrames", 0)) if spy else 0
        for a, b in audible_spans(0, total, mutes):
            yield AudioEvent(bgm["src"], a, b, track=1, volume=bgm.get("volume", .15),
                loop=bgm.get("loop", True), trim_in=a,
                fade_in=bgm.get("fadeInFrames", 45) if a == 0 else resume,
                fade_out=bgm.get("fadeOutFrames", 75) if b == total else 0)
        if spy:
            for cue in bgm.get("cues") or []:
                yield AudioEvent(cue["src"], cue["from"], min(total, cue["from"] + cue["durationInFrames"]),
                    track=4, volume=cue.get("volume", .5), loop=cue.get("loop", True))
