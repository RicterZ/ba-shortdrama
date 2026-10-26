"""Spy-specific placement; exact outlines and animation use template rendering."""
from text_layout import TextElement, prompt_gaps
from ba_text_layout import dialogue


def layout(scene, *, visual_layers=False, editable_captions=False):
    if visual_layers and not editable_captions:
        return
    ep = scene["episode"]
    width, height = ep["width"], ep["height"]
    intro = scene.get("intro") or {}
    intro_end = intro.get("durationInFrames", 0)
    meme = not visual_layers or ep.get("style", {}).get("caption_style", "ba") == "meme"

    def positioned(text, start, end, size, *, track=0, x=.5, top=None,
                   bottom=None, color=None, outline=None, rotation=None):
        center_y = top + size * 1.12 / 2 if top is not None else 1 - bottom - size * 1.12 / 2
        return TextElement(text, start, end, track=track,
            center_x=min(.92, max(.08, x)) * width, center_y=center_y * height,
            font_size=size * height, color=color, outline=outline, rotation=rotation)

    def meme_text(text, start, end, speaker=None, thought=False):
        text = text.replace("。", "")
        size = min(.048 if thought else .098, (.7 if thought else .84) / (max(1, len(text)) * 1.02))
        color = "#ffffff" if thought else scene["characters"].get(speaker, {}).get("color", "#ffffff")
        return positioned(text, start, end, size, bottom=.17 if thought else .06,
            color=color, outline="#0b1119" if thought else color, rotation=-1 if thought else -1.2)

    for index, shot in enumerate(scene["shots"]):
        start = shot["from"]
        end = min(start + shot["durationInFrames"],
                  scene["shots"][index + 1]["from"] if index + 1 < len(scene["shots"]) else ep["durationInFrames"])
        for entry in shot.get("characters", []):
            label = entry.get("label") or {}
            label_end = end
            motion = entry.get("motion") or {}
            if motion.get("startFrame") is not None:
                label_end = min(end, start + int(motion["startFrame"]))
            if label.get("text") and label_end > start:
                secret = label.get("tone") == "secret"
                yield positioned(label["text"], start, label_end, .058, track=1,
                    x=entry.get("x", .5), top=.018, rotation=label.get("rotate", -3),
                    color="#ff9ab7" if secret else "#a9dcff",
                    outline="#ff5f8f" if secret else "#123a5a")
        lines = shot.get("lines") or []
        for line in lines:
            a, b = line["from"], line["from"] + line["durationInFrames"]
            text = line["text"].replace("。", "")
            if not text or b <= a:
                continue
            if line.get("kind") == "thought" or meme:
                yield meme_text(text, a, b, line["speaker"], line.get("kind") == "thought")
            elif b > max(a, intro_end):
                yield dialogue(scene, text, max(a, intro_end), b)
        vote_start = max(start, max((l["from"] + l["durationInFrames"] for l in lines), default=start))
        for tag in shot.get("voteTags") or []:
            entry = next((c for c in shot.get("characters", []) if c["id"] == tag.get("speaker")), None)
            if entry and tag.get("text") and vote_start < end:
                yield positioned(tag["text"], vote_start, end, .05, track=2,
                    x=entry.get("x", .5), top=.62, rotation=-2,
                    color=scene["characters"].get(tag["speaker"], {}).get("color", "#ffffff"), outline="#08111f")
        prompt = (shot.get("choices") or {}).get("prompt")
        if visual_layers and prompt:
            for a, b in prompt_gaps(shot, intro_end):
                if b > a:
                    yield (meme_text(prompt, a, b, (lines or [{}])[-1].get("speaker")) if meme
                           else dialogue(scene, prompt, a, b))
    if not visual_layers and intro.get("title") and intro_end > 0:
        yield TextElement(intro["title"], 0, intro_end)
