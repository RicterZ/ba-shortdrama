import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from sprite_coordinates import read_coordinates


class SpriteCoordinatesTest(unittest.TestCase):
    def test_default_anchors_follow_the_face(self):
        from sprite_coordinates import transfer_anchors
        source = {"x": -50, "y": 0, "width": 100, "height": 200, "face": {"x": 0, "y": 150}}
        target = {"x": -100, "y": 0, "width": 200, "height": 200, "face": {"x": 40, "y": 130}}
        moved = transfer_anchors({"Dot": {"x": .6, "y": .2, "width": .1, "dotX": .3}}, source, target)["Dot"]
        spine_x, spine_top = -50 + .6 * 100, 200 - .2 * 200
        self.assertAlmostEqual(-100 + moved["x"] * 200, spine_x + 40)
        self.assertAlmostEqual(200 - moved["y"] * 200, spine_top - 20)
        self.assertAlmostEqual(moved["width"] * 200, 10)
        self.assertEqual(moved["dotX"], .3)

    @patch("sprite_coordinates.face_centre", return_value={"x": 0, "y": 150})
    def test_native_bounds_not_image_center(self, _face):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skeleton, sprite = root / 'test.skel', root / 'test.png'
            skeleton.write_bytes(b'12345678\x074.2.33' + struct.pack('>ffff', -60, -20, 100, 200))
            Image.new('RGBA', (100, 200)).save(sprite)
            result = read_coordinates(skeleton, sprite)
            self.assertEqual(result['x'], -60)
            self.assertEqual(result['y'], -20)
            self.assertEqual(result['height'], 200)
            self.assertEqual(result['imageWidth'], 100)
            Image.new('RGBA', (200, 200)).save(sprite)
            with self.assertRaises(ValueError):
                read_coordinates(skeleton, sprite)
            skeleton.write_bytes(b'unknown-format')
            with self.assertRaises(ValueError):
                read_coordinates(skeleton, sprite)

    def test_spine_match_report_does_not_treat_aspect_as_identity(self):
        from sprite_coordinates import spine_match_lines
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skel = root / "kivo" / "spine" / "momoi_spr_HD" / "momoi_spr.skel"
            skel.parent.mkdir(parents=True)
            skel.write_bytes(b'12345678\x074.2.33' + struct.pack('>ffff', -60, -20, 100, 200))
            other = root / "kivo" / "spine" / "Momoi_home" / "Momoi_home.skel"
            other.parent.mkdir(parents=True)
            other.write_bytes(b'12345678\x074.2.33' + struct.pack('>ffff', 0, 0, 300, 200))
            sprite = root / "sprites" / "default" / "00.png"
            sprite.parent.mkdir(parents=True)
            Image.new('RGBA', (100, 200)).save(sprite)
            report = "\n".join(spine_match_lines(root))
            self.assertIn("接近 kivo/spine/momoi_spr_HD/momoi_spr.skel", report)
            self.assertIn("不符 kivo/spine/Momoi_home/Momoi_home.skel", report)
            self.assertIn("不会自动写入", report)
            self.assertFalse((root / "profile.yaml").exists())
