import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema
import yaml

import lib
import new_episode
import render


class YamlConfigTest(unittest.TestCase):
    def test_yaml_selects_official_and_preserves_transition_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "episode.yaml"
            path.write_text(
                "id: test\ntemplate: official\nfps: 30\npublication_approved: false\n"
                "transitions:\n  on: scene-change\nui:\n  lineClick: true\n",
                encoding="utf-8",
            )
            config = lib.load_json(path)
        jsonschema.validate(config, lib.load_json(lib.SCHEMAS / "episode.json"))
        self.assertEqual(config["template"], "official")
        self.assertTrue(render.TEMPLATES[config["template"]].is_file())
        self.assertEqual(config["transitions"]["on"], "scene-change")
        self.assertIs(config["publication_approved"], False)
        self.assertIs(config["ui"]["lineClick"], True)

    def test_legacy_json_config_still_loads(self):
        config = {"template": "official", "transitions": {"on": "none"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "episode.yaml"
            lib.write_json(path, config)
            self.assertEqual(lib.load_json(path), config)

    def test_new_episode_writes_yaml_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(lib, "VIDEOS", Path(tmp)), patch.object(lib, "read_character"), patch(
                "sys.argv", ["new_episode.py", "test", "--template", "official"]
            ):
                new_episode.main()
            path = Path(tmp) / "test" / "episode.yaml"
            self.assertIn("template: official", path.read_text(encoding="utf-8"))
            config = lib.load_json(path)
            jsonschema.validate(config, lib.load_json(lib.SCHEMAS / "episode.json"))
            self.assertEqual(config["template"], "official")

    def test_yaml_rejects_object_construction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "episode.yaml"
            path.write_text("!!python/object:builtins.object {}", encoding="utf-8")
            with self.assertRaises(yaml.constructor.ConstructorError):
                lib.load_json(path)

    def test_json_artifacts_stay_strict_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scene.json"
            path.write_text("template: official", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                lib.load_json(path)


if __name__ == "__main__":
    unittest.main()
