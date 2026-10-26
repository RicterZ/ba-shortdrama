"""Official template text placement for native editable captions."""
from text_layout import TextElement, prompt_gaps
from ba_text_layout import dialogue


def layout(scene, *, visual_layers=False, editable_captions=False):
    intro = scene.get("intro") or {}
    intro_end = intro.get("durationInFrames", 0)
    if visual_layers and not editable_captions:
        return
    for shot in scene["shots"]:
        for line in shot.get("lines", []):
            start = max(line["from"], intro_end)
            end = min(line["from"] + line["durationInFrames"], shot["from"] + shot["durationInFrames"])
            if line["text"] and end > start:
                yield dialogue(scene, line["text"], start, end)
        prompt = (shot.get("choices") or {}).get("prompt")
        if prompt:
            for a, b in prompt_gaps(shot, intro_end):
                if b > a:
                    yield dialogue(scene, prompt, a, b)
