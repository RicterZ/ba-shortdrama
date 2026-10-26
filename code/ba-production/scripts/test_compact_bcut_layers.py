"""Lossless alpha encoding must preserve every source frame and transparent gap."""
import shutil
import tempfile
import unittest
from pathlib import Path

import av
from PIL import Image

from compact_bcut_layers import compact_layers


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
class CompactLayersTests(unittest.TestCase):
    def test_rgba_timing_and_gaps(self):
        with tempfile.TemporaryDirectory() as folder:
            assets = Path(folder)
            spans, expected, cursor = [], [], 0
            for index in range(10):
                image = Image.new("RGBA", (64, 32), (index * 20, 50, 200, 30 + index * 20))
                name = f"{index}.png"
                image.save(assets / name)
                duration = index % 3 + 1
                spans.append(dict(layer="character", label="character", name=name,
                                  startFrame=cursor, endFrame=cursor + duration))
                expected.extend([image.tobytes()] * duration)
                cursor += duration
            spans.append({**spans[-1], "startFrame": cursor + 1, "endFrame": cursor + 4})
            scene = {"episode": {"fps": 30, "durationInFrames": cursor + 4}, "shots": [{"from": 0}]}
            packed = compact_layers(spans, scene, assets)
            self.assertEqual(len(packed), 2)
            self.assertEqual(packed[0]["endFrame"], cursor)
            self.assertEqual(packed[1]["startFrame"], cursor + 1)
            with av.open(str(assets / packed[0]["name"])) as container:
                decoded = [frame.to_ndarray(format="rgba").tobytes() for frame in container.decode(video=0)]
            self.assertEqual(decoded, expected)

    def test_static_hold_after_entrance_stays_an_image(self):
        with tempfile.TemporaryDirectory() as folder:
            assets = Path(folder)
            spans = []
            for index in range(10):
                Image.new("RGBA", (8, 8), (index * 20, 0, 0, 255)).save(assets / f"{index}.png")
                spans.append(dict(layer="character", label="character", name=f"{index}.png",
                                  startFrame=index, endFrame=index + 1))
            spans.append({**spans[-1], "name": "9.png", "startFrame": 10, "endFrame": 100})
            spans.append({**spans[-1], "name": "0.png", "startFrame": 100, "endFrame": 102})
            scene = {"episode": {"fps": 30, "durationInFrames": 102}, "shots": [{"from": 0}]}
            packed = compact_layers(spans, scene, assets)
            self.assertEqual([(s["startFrame"], s["endFrame"], s["name"].endswith(".mov")) for s in packed],
                             [(0, 10, True), (10, 100, False), (100, 102, False)])


if __name__ == "__main__":
    unittest.main()
