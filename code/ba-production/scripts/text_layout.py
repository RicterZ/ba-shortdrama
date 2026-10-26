"""Template-owned text layout, expressed in canvas pixels and source frames."""
from __future__ import annotations

from dataclasses import dataclass
import math
from bcut_processor import load_processor


@dataclass(frozen=True)
class TextElement:
    text: str
    start: int
    end: int
    track: int = 0
    center_x: float | None = None
    center_y: float | None = None
    font_size: float | None = None
    color: str | None = None
    outline: str | None = None
    rotation: float | None = None
    alignment: int | None = None
    draw_outline: bool | None = None

    def validate(self):
        if not isinstance(self.text, str):
            raise ValueError("Text content must be a string")
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0
               for v in (self.start, self.end, self.track)) or self.end <= self.start:
            raise ValueError("Invalid text frame range or track")
        for value in (self.center_x, self.center_y, self.font_size, self.rotation):
            if value is not None and not math.isfinite(value):
                raise ValueError("Text geometry must be finite")
        if self.font_size is not None and self.font_size <= 0:
            raise ValueError("Text font size must be positive")


def text_elements(scene, *, visual_layers=False, editable_captions=False):
    """Discover a processor beside the template, without a template-name registry."""
    try:
        processor = load_processor(scene, "text_layout.py")
    except ValueError as exc:
        if "has no text_layout.py" in str(exc):
            return []
        raise
    elements = list(processor.layout(scene, visual_layers=visual_layers,
                                     editable_captions=editable_captions))
    for element in elements:
        if not isinstance(element, TextElement):
            raise ValueError("Text processors must return TextElement objects")
        element.validate()
    return elements


def prompt_gaps(shot, intro_end):
    cursor = max(shot["from"], intro_end)
    end = shot["from"] + shot["durationInFrames"]
    for line in sorted(shot.get("lines", []), key=lambda line: line["from"]):
        if line["from"] > cursor:
            yield cursor, min(line["from"], end)
        cursor = max(cursor, line["from"] + line["durationInFrames"])
        if cursor >= end:
            return
    if cursor < end:
        yield cursor, end
