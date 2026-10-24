"""Read Spine 4.2 export bounds for a matching, uncropped standing PNG."""
import hashlib
import math
import struct
from pathlib import Path
from PIL import Image


def read_coordinates(skeleton: Path, sprite: Path) -> dict:
    raw = skeleton.read_bytes()
    # Spine 4.2: 8-byte hash, length-prefixed version string, four BE floats.
    if len(raw) < 31 or raw[8:15] != b"\x074.2.33":
        raise ValueError("Only verified Spine 4.2.33 export headers are supported")
    x, y, width, height = struct.unpack_from(">ffff", raw, 15)
    if not all(math.isfinite(v) for v in (x, y, width, height)) or min(width, height) <= 0:
        raise ValueError("Invalid Spine bounds")
    with Image.open(sprite) as image:
        iw, ih = image.size
    if abs((iw / ih) / (width / height) - 1) > .02:
        raise ValueError("PNG and Spine bounds differ: use the matching uncropped standing export")
    return {"x": x, "y": y, "width": width, "height": height,
            "imageWidth": iw, "imageHeight": ih,
            "source": skeleton.name, "sha256": hashlib.sha256(raw).hexdigest()}
