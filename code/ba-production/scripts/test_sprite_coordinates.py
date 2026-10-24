import struct
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from sprite_coordinates import read_coordinates


class SpriteCoordinatesTest(unittest.TestCase):
    def test_native_bounds_not_image_center(self):
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
