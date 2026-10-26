"""Generic image geometry and linear movement, baked to portable transparent spans."""
from dataclasses import dataclass
import hashlib
import math

from PIL import Image, ImageOps


@dataclass(frozen=True)
class ImagePose:
    frame: int
    x: float
    y: float
    width: float
    height: float
    opacity: float = 1
    rotation: float = 0


@dataclass(frozen=True)
class ImageElement:
    src: str
    start: int
    end: int
    layer: str
    poses: tuple[ImagePose, ...]
    fit: str = "stretch"
    mirror: bool = False

    def validate(self, total):
        if not isinstance(self.src, str) or not self.src or not isinstance(self.layer, str) or not self.layer:
            raise ValueError("Image source and layer are required")
        if any(not isinstance(v, int) or isinstance(v, bool) for v in (self.start, self.end)) or not 0 <= self.start < self.end <= total:
            raise ValueError("Invalid image frame range")
        if self.fit not in {"stretch", "cover", "contain"} or not self.poses:
            raise ValueError("Invalid image fit or missing poses")
        previous = -1
        for pose in self.poses:
            if not isinstance(pose.frame, int) or isinstance(pose.frame, bool) or pose.frame <= previous:
                raise ValueError("Image poses must have increasing frame numbers")
            if any(not math.isfinite(v) for v in (pose.x, pose.y, pose.width, pose.height, pose.opacity, pose.rotation)):
                raise ValueError("Image geometry must be finite")
            if pose.width <= 0 or pose.height <= 0 or not 0 <= pose.opacity <= 1:
                raise ValueError("Invalid image size or opacity")
            previous = pose.frame


def pose_at(element, frame):
    before = element.poses[0]
    for after in element.poses[1:]:
        if frame < after.frame:
            t = max(0, min(1, (frame - before.frame) / (after.frame - before.frame)))
            return ImagePose(frame, **{key: getattr(before, key) + t * (getattr(after, key) - getattr(before, key))
                                      for key in ("x", "y", "width", "height", "opacity", "rotation")})
        before = after
    return before


def render_images(scene, raws, assets, elements):
    """Preserve source-frame movement without relying on Bcut keyframe variants."""
    ep = scene["episode"]
    elements = list(elements)
    layer_order = list(dict.fromkeys(element.layer for element in elements))
    for element in elements:
        element.validate(ep["durationInFrames"])
    spans = []
    for layer in layer_order:
        previous = None
        for element in sorted((e for e in elements if e.layer == layer), key=lambda e: e.start):
            if previous and previous["endFrame"] > element.start:
                raise ValueError(f"Overlapping images in layer {layer}")
            source = (raws / element.src).resolve()
            if not source.is_relative_to(raws.resolve()) or not source.is_file():
                raise ValueError(f"Missing or unsafe image: {element.src}")
            with Image.open(source) as im:
                original = im.convert("RGBA")
            if element.mirror:
                original = ImageOps.mirror(original)
            frames = range(element.start, element.end) if len(element.poses) > 1 else [element.start]
            for frame in frames:
                pose = pose_at(element, frame)
                size = (max(1, round(pose.width)), max(1, round(pose.height)))
                if element.fit == "cover":
                    image = ImageOps.fit(original, size, method=Image.Resampling.LANCZOS)
                elif element.fit == "contain":
                    image = ImageOps.contain(original, size, method=Image.Resampling.LANCZOS)
                else:
                    image = original.resize(size, Image.Resampling.LANCZOS)
                image.putalpha(image.getchannel("A").point(lambda a: round(a * pose.opacity)))
                if pose.rotation:
                    image = image.rotate(-pose.rotation, expand=True, resample=Image.Resampling.BICUBIC)
                canvas = Image.new("RGBA", (ep["width"], ep["height"]))
                canvas.alpha_composite(image, (round(pose.x - image.width / 2), round(pose.y - image.height / 2)))
                name = "image-" + hashlib.sha256(canvas.tobytes()).hexdigest()[:24] + ".png"
                destination = assets / name
                if not destination.exists():
                    canvas.save(destination)
                end = frame + 1 if len(element.poses) > 1 else element.end
                if previous and previous["name"] == name and previous["endFrame"] == frame:
                    previous["endFrame"] = end
                else:
                    previous = {"layer": layer, "label": layer, "name": name,
                                "startFrame": frame, "endFrame": end}
                    spans.append(previous)
    return spans
