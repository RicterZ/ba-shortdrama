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
