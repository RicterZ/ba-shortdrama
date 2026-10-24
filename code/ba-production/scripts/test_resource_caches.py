import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fetch_kivo as kivo
import fetch_sprites as sprites


class ResourceCacheTests(unittest.TestCase):
    def test_student_alias_and_music_catalog_are_cached_until_force(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            student = {"id": 2, "family_name_en": "Saiba", "given_name_en": "Momoi"}
            with patch.object(kivo, "CACHE", root / "cache"), patch.object(kivo, "CHARACTERS", root / "characters"), patch.object(kivo, "api", return_value=student) as api:
                self.assertEqual(kivo.resolve_student("2"), student)
                self.assertEqual(kivo.resolve_student("2"), student)
                api.assert_called_once_with("/data/students/2")

            with patch.object(kivo, "CACHE", root / "cache"), patch.object(kivo, "api", return_value={"music": [{"id": 1}], "max_page": 1}) as api:
                self.assertEqual(kivo.music_catalog(), [{"id": 1}])
                self.assertEqual(kivo.music_catalog(), [{"id": 1}])
                self.assertEqual(api.call_count, 1)
                kivo.music_catalog(force=True)
                self.assertEqual(api.call_count, 2)

    def test_sprite_page_and_image_index_cache_and_force(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = {"parse": {"wikitext": "page"}}
            with patch.object(sprites, "CACHE", root / "cache"), patch.object(sprites, "api", return_value=payload) as api:
                self.assertEqual(sprites.wikitext("Momoi"), "page")
                self.assertEqual(sprites.wikitext("Momoi"), "page")
                self.assertEqual(api.call_count, 1)
                sprites.wikitext("Momoi", force=True)
                self.assertEqual(api.call_count, 2)

            with patch.object(sprites, "CACHE", root / "cache"), patch.object(sprites, "api", return_value={"query": {"pages": []}}) as api:
                self.assertEqual(sprites.image_urls(["Momoi_00.png"]), {})
                self.assertEqual(sprites.image_urls(["Momoi_00.png"]), {})
                self.assertEqual(api.call_count, 1)
                sprites.image_urls(["Momoi_00.png"], force=True)
                self.assertEqual(api.call_count, 2)


if __name__ == "__main__":
    unittest.main()
