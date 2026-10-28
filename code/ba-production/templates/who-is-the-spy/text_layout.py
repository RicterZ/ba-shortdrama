"""Spy-specific placement; exact outlines and animation use template rendering."""
from text_layout import TextElement, prompt_gaps
from ba_text_layout import dialogue

CAPTION_BREAKS = "，。；：！？、）”…"


def wrap_caption(text, max_chars, max_lines):
    """Same break rule as the Remotion caption: balanced, punctuation first."""
    chars = list(text)
    if len(chars) <= max_chars:
        return [text]
    if max_lines == 2 and len(chars) <= max_chars * 2:
        ideal = len(chars) / 2
        best, best_score = max_chars, float("-inf")
        for cut in range(len(chars) - max_chars, max_chars + 1):
            score = (4 if chars[cut - 1] in CAPTION_BREAKS else 0) - abs(cut - ideal) / 2
            if score > best_score:
                best, best_score = cut, score
        return ["".join(chars[:best]), "".join(chars[best:])]
    lines = []
    start = 0
    while start < len(chars) and len(lines) < max_lines:
        if len(chars) - start <= max_chars:
            lines.append("".join(chars[start:]))
            start = len(chars)
            break
        cut = start + max_chars
        for i in range(cut, start + max_chars // 2, -1):
            if chars[i - 1] in CAPTION_BREAKS:
                cut = i
                break
        lines.append("".join(chars[start:cut]))
        start = cut
    if start < len(chars):
        lines[-1] += "".join(chars[start:])
    return lines


def layout(scene, *, visual_layers=False, editable_captions=False):
    if visual_layers and not editable_captions:
        return
    ep = scene["episode"]
    width, height = ep["width"], ep["height"]
    intro = scene.get("intro") or {}
    intro_end = intro.get("durationInFrames", 0)
    meme = not visual_layers or ep.get("style", {}).get("caption_style", "ba") == "meme"

    def positioned(text, start, end, size, *, track=0, x=None, top=None,
                   bottom=None, color=None, outline=None, rotation=None):
        center_y = top + size * 1.12 / 2 if top is not None else 1 - bottom - size * 1.12 / 2
        return TextElement(text, start, end, track=track,
            center_x=None if x is None else min(.92, max(.08, x)) * width,
            center_y=center_y * height,
            font_size=size * height, color=color, outline=outline, rotation=rotation)

    def meme_text(text, start, end, speaker=None, thought=False):
        text = text.replace("。", "")
        color = "#ffffff" if thought else scene["characters"].get(speaker, {}).get("color", "#ffffff")
        # Fixed-size narration captions wrap at the configured width instead of
        # shrinking to a single line, mirroring MemeCaption in index.tsx.
        fixed = None if thought else ep.get("style", {}).get("caption_size")
        if fixed:
            subtitle = ep.get("subtitle") or {}
            lines = wrap_caption(text, int(subtitle.get("max_chars_per_line", 26)),
                                 int(subtitle.get("max_lines", 2)))
            # Same shrink-to-fit clamp as MemeCaption: a line wider than the
            # caption box pulls the whole block down a notch.
            longest = max(len(line) for line in lines)
            size = min(fixed, width / height * .84 / (longest * 1.02))
            bottom = .045
            block = len(lines) * 1.34 * size
            return TextElement("\n".join(lines), start, end, track=0,
                center_x=.5 * width, center_y=(1 - bottom) * height - block * height / 2,
                font_size=size * height, color=color, outline="#ffffff", rotation=0)
        size = min(.048 if thought else .098, (.7 if thought else .84) / (max(1, len(text)) * 1.02))
        return positioned(text, start, end, size, bottom=.17 if thought else .06,
            color=color, outline="#0b1119" if thought else "#ffffff", rotation=-1 if thought else -1.2)

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
