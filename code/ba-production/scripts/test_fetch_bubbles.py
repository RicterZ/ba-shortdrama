import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import fetch_bubbles


class BubbleFetchTest(unittest.TestCase):
    def test_existing_files_are_preserved_and_new_provenance_is_appended(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "data/effects/ba"
            folder.mkdir(parents=True)
            for preset in fetch_bubbles.PRESETS.values():
                for name in preset["images"]:
                    (folder / name).write_bytes(b"existing-user-resource")
            original = {"path": "custom.png", "note": "keep"}
            (folder / "bubble-sources.json").write_text(json.dumps([original]))
            with patch.object(fetch_bubbles.lib, "ROOT", root), \
                    patch.object(fetch_bubbles.requests, "get") as get, \
                    patch.object(fetch_bubbles.fetch_kivo, "fetch_sfx") as sfx:
                fetch_bubbles.main()
                fetch_bubbles.main()
                get.assert_not_called()
                self.assertEqual(len(sfx.call_args.args[0]), 20)
            records = json.loads((folder / "bubble-sources.json").read_text())
            self.assertEqual(records[0], original)
            self.assertEqual(len(records), len({item["path"] for item in records}))
            self.assertEqual((folder / "Emoticon_Shy.png").read_bytes(), b"existing-user-resource")

    def test_non_png_response_is_not_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            response = Mock(content=b"<html>error</html>")
            with patch.object(fetch_bubbles.lib, "ROOT", Path(tmp)), \
                    patch.object(fetch_bubbles.requests, "get", return_value=response), \
                    self.assertRaises(SystemExit):
                fetch_bubbles.main()
            self.assertEqual(list(Path(tmp).rglob("*.png")), [])


if __name__ == "__main__":
    unittest.main()
