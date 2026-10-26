"""BA scene interpretation and static preview; Bcut writes only generic events."""
import math
from pathlib import Path
import uuid
from PIL import Image, ImageEnhance, ImageOps
import lib
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


def smooth(t):
    return t * t * (3 - 2 * t)


def placement(entry, shot, frame, height):
    """Stage position at a frame, following CharacterFigure's motion, hops and entrance."""
    local = frame - int(shot["from"])
    px, ground, scale = entry.get("x", .5), entry.get("bottom", -0.25), entry.get("scale", 1)
    lift = 0
    motion = entry.get("motion")
    if motion:
        start = motion.get("startFrame", 0)
        end = max(start + 1, motion.get("endFrame", shot["durationInFrames"]))
        ends = [(motion.get(f"from{k}", entry.get(k.lower(), d)), motion.get(f"to{k}", entry.get(k.lower(), d)))
                for k, d in (("X", .5), ("Bottom", -0.25), ("Scale", 1))]
        hops = max(0, int(motion.get("hops", 0)))
        if hops > 1:
            span = end - start
            hop = span / hops
            position = min(span, max(0, local - start)) / hop
            index = min(hops - 1, int(position))
            u = 1 if local >= end else position - index
            t = (index + smooth(u)) / hops
            lift = math.sin(math.pi * u) * motion.get("hopLift", .05)
        else:
            raw = min(1, max(0, (local - start) / (end - start)))
            t = raw if motion.get("ease") == "linear" else smooth(raw)
        px, ground, scale = (a + (b - a) * t for a, b in ends)
    # spring({damping: 200}) settles in 16 frames without overshoot.
    entrance = 1 - (1 - min(1, max(0, local / 16))) ** 3
    tx = 0
    kind = entry.get("entrance")
    if kind in ("slide-in-right", "slide-in-left"):
        tx = (1 - entrance) * max(180, height * .35) * (1 if kind == "slide-in-right" else -1)
    return px, ground + lift, scale, tx, entrance if kind == "fade-in" else 1


_ACTIONS = None


def action_pose(entry, local, fps):
    """Frozen character-actions.mjs preset: x, y, angle, scale, opacity, originX, originY."""
    global _ACTIONS
    cue = max((c for c in entry.get("actions") or [] if c["startFrame"] <= local),
              key=lambda c: c["startFrame"], default=None)
    if cue is None:
        return 0, 0, 0, 1, 1, .5, 1
    if _ACTIONS is None:
        _ACTIONS = lib.load_json(Path(__file__).parents[1] / "templates/character-action-keyframes.json")
    keys = _ACTIONS["presets"][cue["name"]]
    position = min(len(keys) - 1, (local - cue["startFrame"]) / fps * _ACTIONS["rate"])
    a, b = keys[int(position)], keys[min(len(keys) - 1, int(position) + 1)]
    u = position - int(position)
    return tuple(p + (q - p) * u for p, q in zip(a[:5], b[:5])) + tuple(a[5:])


def flip_at(entry, local):
    """CharacterFigure's scaleX: +1 as drawn, -1 mirrored, animated through 0 by turns."""
    flip = -1 if entry.get("facing") == "left" else 1
    for turn in entry.get("turns") or []:
        target = -1 if turn.get("to") == "left" else 1
        start = turn.get("startFrame", 0)
        duration = max(1, turn.get("durationInFrames", 6))
        if local < start:
            break
        if local >= start + duration:
            flip = target
            continue
        flip += (target - flip) * smooth((local - start) / duration)
    return flip


def facing_spans(entry, shot, start, end):
    """Split where a turn crosses scaleX 0, so each part bakes the facing it shows."""
    base = int(shot["from"])
    spans, a = [], start
    sign = flip_at(entry, a - base) < 0
    for frame in range(start + 1, end):
        now = flip_at(entry, frame - base) < 0
        if now != sign:
            spans.append((a, frame, "left" if sign else "right"))
            a, sign = frame, now
    spans.append((a, end, "left" if sign else "right"))
    return spans


def pose_keyframes(entry, shot, start, end, width, height, aspect=0.5, fps=30):
    """Bcut transform keys relative to the pose baked at the entry's resting mark.

    CSS: translate(stage + action) scale(m) rotate(a) scaleX(|flip|) about the
    action origin. Bcut: scale/rotate a full-canvas layer about the canvas
    centre C, then translate t (half-canvas units, y up). With the bake scaled
    by s0 about its bottom centre B0 the two agree when
    t = O - C + M (off_b - off_o) + M/s0 (C - B0).
    """
    kind = entry.get("entrance")
    motion = entry.get("motion")
    base = int(shot["from"])
    frames = {start, end}
    if kind in ("fade-in", "slide-in-right", "slide-in-left"):
        frames.update(range(base, base + 17, 2))
    if motion:
        a = base + motion.get("startFrame", 0)
        b = base + max(motion.get("startFrame", 0) + 1, motion.get("endFrame", shot["durationInFrames"]))
        step = 2 if motion.get("hops", 0) > 1 else 3
        frames.update(range(a, b, step))
        frames.add(b)
    for turn in entry.get("turns") or []:
        a = base + turn.get("startFrame", 0)
        frames.update(range(a, a + max(1, turn.get("durationInFrames", 6)) + 1))
    for cue in entry.get("actions") or []:
        a = base + cue["startFrame"]
        frames.update(range(a, a + 2 * fps + 1))
    box = height * entry.get("height", 1.08)
    sprite_w = box * aspect
    s0 = entry.get("scale", 1)
    c0 = (width * entry.get("x", .5), height * (1 - entry.get("bottom", -0.25)) - box / 2)
    b0 = (c0[0], c0[1] + box / 2)
    cx, cy = width / 2, height / 2
    keys = []
    for frame in sorted(f for f in frames if start <= f <= end):
        local = frame - base
        x, bottom, scale, tx, opacity = placement(entry, shot, frame, height)
        ax, ay, angle, ak, aop, ox, oy = action_pose(entry, local, fps)
        f = abs(flip_at(entry, local))
        m = scale * ak
        rad = math.radians(angle)
        cos, sin = math.cos(rad), math.sin(rad)
        matrix = lambda vx, vy, k: (k * (cos * f * vx - sin * vy), k * (sin * f * vx + cos * vy))
        off_o = ((ox - .5) * sprite_w, (oy - .5) * box)
        origin = (width * x + tx + ax * sprite_w + off_o[0],
                  height * (1 - bottom) - box / 2 + ay * box + off_o[1])
        p = matrix(0 - off_o[0], box / 2 - off_o[1], m)
        q = matrix(cx - b0[0], cy - b0[1], m / s0)
        t = (origin[0] - cx + p[0] + q[0], origin[1] - cy + p[1] + q[1])
        keys.append({"frame": frame, "transX": round(2 * t[0] / width, 5),
                     "transY": round(-2 * t[1] / height, 5),
                     "scaleX": round(f * m / s0, 5), "scale": round(m / s0, 5),
                     "rotation": round(angle, 4), "opacity": round(opacity * aop, 4)})
    if all(abs(k["transX"]) < 1e-5 and abs(k["transY"]) < 1e-5 and k["scale"] == k["scaleX"] == 1
           and k["rotation"] == 0 and k["opacity"] == 1 for k in keys):
        return []
    return keys


def dim_spans(entry, shot, start, end):
    """Official dims a character while someone else speaks."""
    points = {start, end}
    for line in shot.get("lines") or []:
        for at in (int(line["from"]), int(line["from"]) + int(line["durationInFrames"])):
            if start < at < end:
                points.add(at)
    ordered = sorted(points)
    spans = []
    for a, b in zip(ordered, ordered[1:]):
        active = next((l for l in shot.get("lines") or []
                       if int(l["from"]) <= a < int(l["from"]) + int(l["durationInFrames"])), None)
        dimmed = bool(active) and active.get("speaker") != entry["id"]
        if spans and spans[-1][2] == dimmed:
            spans[-1] = (spans[-1][0], b, dimmed)
        else:
            spans.append((a, b, dimmed))
    return spans


def key_at(keys, frame):
    """Linear interpolation between sampled keys, held beyond the ends."""
    before = [k for k in keys if k["frame"] <= frame]
    after = [k for k in keys if k["frame"] >= frame]
    a = before[-1] if before else after[0]
    b = after[0] if after else before[-1]
    u = 0 if b["frame"] == a["frame"] else (frame - a["frame"]) / (b["frame"] - a["frame"])
    return {name: frame if name == "frame" else round(a[name] + (b[name] - a[name]) * u, 5)
            for name in a}


def static_spans(scene, assets, copied, *, spy=False):
    width, height = scene["episode"]["width"], scene["episode"]["height"]
    spans = []
    def image(name, start, end, index, label, keyframes=()):
        if end > start:
            inside = [k for k in keyframes if start < k["frame"] < end]
            edges = [key_at(keyframes, f) for f in (start, end)] if keyframes else []
            spans.append({"name": name, "startFrame": start, "endFrame": end,
                          "layer": str(index), "label": label,
                          "keyframes": edges[:1] + inside + edges[1:]})
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
            reference = sprites.get(entry.get("emotion")) or sprites.get("default") or next(iter(sprites.values()))
            with Image.open(assets / copied(reference)) as im:
                aspect = im.width / im.height
            keys = pose_keyframes(entry, shot, start_frame, end_frame, width, height,
                                  aspect, scene["episode"]["fps"])
            baked = {}
            for a, b, emotion in expression_spans(entry, shot, start_frame, end_frame):
                original = sprites.get(emotion) or sprites.get("default")
                if not original:
                    raise ValueError(f"{entry['id']}/{outfit_id} has no sprite for {emotion}")
                for c, d, dimmed in (dim_spans(entry, shot, a, b) if not spy else [(a, b, False)]):
                    for e, g, facing in facing_spans(entry, shot, c, d):
                        if (original, dimmed, facing) not in baked:
                            baked[original, dimmed, facing] = pose(copied(original), entry, assets, width, height,
                                spotlight_dim=bool(focus) and entry["id"] != focus, speaker_dim=dimmed,
                                facing=facing)
                        image(baked[original, dimmed, facing], e, g, track_index,
                              f"{entry['id']} {emotion}" + (" 压暗" if dimmed else ""), keys)
    return spans


def pose(original_name, entry, assets, width, height, *, spotlight_dim=False, speaker_dim=False,
         facing=None):
    with Image.open(assets / original_name) as im:
        im = im.convert("RGBA")
        scale = entry.get("scale", 1)
        h = max(1, round(height * entry.get("height", 1.08) * scale))
        w = max(1, round(im.width * h / im.height))
        im = im.resize((w, h), Image.Resampling.LANCZOS)
        if (facing or entry.get("facing")) == "left":
            im = ImageOps.mirror(im)
        if spotlight_dim:
            im = tone(im, brightness=0.38, color=0.28)
        elif speaker_dim:
            im = tone(im, brightness=0.66, color=0.82)
        canvas = Image.new("RGBA", (width, height))
        # CharacterFigure scales about the bottom centre of its unscaled box.
        ground = height * (1 - entry.get("bottom", -0.25))
        canvas.paste(im, (round(width * entry.get("x", .5) - w / 2), round(ground - h)))
        name = f"pose-{uuid.uuid4().hex}.png"
        canvas.save(assets / name)
    return name


def chrome_stills(scene):
    """Title card and per-speaker dialogue box, each rendered once as a still."""
    from text_layout import prompt_gaps
    stills = []
    intro_end = (scene.get("intro") or {}).get("durationInFrames", 0)
    if intro_end > 0:
        # Intro fades its band in over frames 2-26 and everything out in the last 14.
        stills.append({"layer": "intro", "frame": max(0, min(30, intro_end - 15)),
                       "label": "片头标题", "spans": [(0, intro_end)],
                       "fade": [(0, 0), (min(18, intro_end), 1),
                                (max(18, intro_end - 14), 1), (intro_end, 0)]})
    boxes = {}
    shots = scene["shots"]
    for index, shot in enumerate(shots):
        _, visible_end = visible_bounds(shots, index)
        lines = shot.get("lines", [])
        spans = [(line["speaker"], line["from"], line["from"] + line["durationInFrames"], line)
                 for line in lines if line.get("speaker")]
        prompt = (shot.get("choices") or {}).get("prompt")
        speaker = lines[-1]["speaker"] if lines else (shot.get("characters") or [{}])[0].get("id")
        if prompt and speaker:
            spans += [(speaker, a, b, None) for a, b in prompt_gaps(shot, intro_end)]
        for who, a, b, line in spans:
            a, b = max(a, intro_end), min(b, visible_end)
            if b <= a:
                continue
            box = boxes.setdefault(who, {"layer": "dialogue", "frame": None,
                                         "label": f"对话框 {who}", "spans": []})
            if box["spans"] and box["spans"][-1][1] == a:
                box["spans"][-1] = (box["spans"][-1][0], b)
            else:
                box["spans"].append((a, b))
            # A frame after the box's entrance while text is still typing (no ▼ cursor).
            frame = max(a + 2, shot["from"] + 10)
            typing_end = a + 2 + scene["episode"]["fps"] / 15 * len(line["text"]) if line else b
            if frame < min(b, typing_end) and box["frame"] is None:
                box["frame"] = frame
            box.setdefault("fallback", a)
    title = stills
    stills = []
    for box in boxes.values():
        if box["frame"] is None:
            box["frame"] = box["fallback"]
        box.pop("fallback")
        stills.append(box)
    return stills + ui_layers(scene, intro_end) + title


def ui_layers(scene, intro_end):
    """Cursor loop, in-game chrome, bubbles, buttons and choices.

    "frame" layers are one still; "animated" layers render every frame of their
    spans (holds stay PNG, motion becomes MOV); "loop" renders one cycle and tiles it.
    """
    fps = scene["episode"]["fps"]
    total = scene["episode"]["durationInFrames"]
    shots = scene["shots"]
    cursor = []
    for index, shot in enumerate(shots):
        _, visible_end = visible_bounds(shots, index)
        for line in shot.get("lines", []):
            # The ▼ appears once the 15 glyph/s typewriter finishes.
            a = max(intro_end, math.ceil(line["from"] + 2 + fps / 15 * (len(line["text"]) - 1)))
            b = min(line["from"] + line["durationInFrames"], visible_end)
            if b > a:
                cursor.append((a, b))
    layers = []
    if cursor:
        # |sin(frame / 10)| repeats every 10π ≈ 31.4 frames.
        layers.append({"layer": "cursor", "loop": 31, "label": "▼ 继续提示", "spans": cursor})
    if intro_end < total:
        layers.append({"layer": "chrome", "frame": intro_end, "label": "界面按钮",
                       "spans": [(intro_end, total)]})
    presets = lib.load_json(Path(__file__).parents[1] / "templates/bubble-presets.json")
    bubbles, buttons, choices = {}, [], []
    for index, shot in enumerate(shots):
        _, visible_end = visible_bounds(shots, index)
        base = int(shot["from"])
        for entry in shot.get("characters", []):
            cues = sorted(entry.get("bubbles") or [], key=lambda cue: cue["startFrame"])
            for cue, after in zip(cues, cues[1:] + [None]):
                a = base + cue["startFrame"]
                b = min(visible_end, a + math.ceil(presets[cue["name"]]["seconds"] * fps) + 1,
                        base + after["startFrame"] if after else total)
                if b > a:
                    bubbles.setdefault(entry["id"], []).append((a, b))
        if shot.get("buttons") and visible_end > max(base, intro_end):
            buttons.append((max(base, intro_end), visible_end))
        choice = shot.get("choices") or {}
        if choice.get("options"):
            start = max(0, choice.get("fromFrame", 0))
            select = max(start, choice.get("selectFrame", start + 30))
            hide = max(select + 1, choice.get("hideFrame", select + 22))
            a, b = max(base + start, intro_end), min(visible_end, base + hide)
            if b > a:
                choices.append((a, b))
    for who, spans in bubbles.items():
        layers.append({"layer": f"bubble:{who}", "animated": True, "label": f"气泡 {who}", "spans": spans})
    if buttons:
        layers.append({"layer": "buttons", "animated": True, "label": "按钮", "spans": buttons})
    if choices:
        layers.append({"layer": "choices", "animated": True, "label": "选项", "spans": choices})
    return layers


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
    # The spy keyframe draft draws no bubbles or controls, so it has no effect sounds.
    if visual_layers or not spy:
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
