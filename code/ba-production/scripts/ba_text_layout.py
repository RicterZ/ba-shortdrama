"""BA template typography approximation for native captions, not the Bcut writer."""
from text_layout import TextElement


def dialogue(scene, text, start, end):
    """Shared BA textbox approximation; precise typography stays in rendered layers."""
    width, height = scene["episode"]["width"], scene["episode"]["height"]
    lines = text.splitlines() or [text]
    advance = max(sum(1 if ord(c) > 255 else .55 for c in row) for row in lines)
    return TextElement(text, start, end,
        center_x=.09 * width + advance * height * .038 / 2,
        center_y=height * (.76 + .038 * len(lines) * 1.12 / 2),
        font_size=height * .03192, alignment=0, draw_outline=False)


