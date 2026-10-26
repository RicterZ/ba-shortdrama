"""Preview scene builder: one bubble or one action, no episode."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lib
import preview_fx


def write_character(root: Path, *, spine: bool) -> None:
    character = root / "data" / "characters" / "demo"
    sprite = character / "sprites" / "default" / "00.png"
    sprite.parent.mkdir(parents=True)
    Image.new("RGBA", (100, 200), (200, 80, 120, 255)).save(sprite)
    outfits = {
        "default": {
            "name": "标准",
            "sprites": {"default": {"path": "sprites/default/00.png"}},
        }
    }
    if spine:
        skel = character / "kivo" / "spine" / "demo" / "demo.skel"
        skel.parent.mkdir(parents=True)
        skel.write_bytes(b"12345678\x074.2.33" + struct.pack(">ffff", -10, -20, 100, 200))
        outfits["default"]["spine"] = "kivo/spine/demo/demo.skel"
    lib.write_json(
        character / "profile.yaml",
        {
            "schema_version": 2,
            "id": "demo",
            "name": "测试",
            "color": "#112233",
            "default_outfit": "default",
            "outfits": outfits,
        },
    )
    for image in ("Emoticon_Balloon_N.png", "Emoticon_Heart.png"):
        dest = root / "data" / "effects" / "ba" / image
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x89PNG\r\n\x1a\npng")


class PreviewFxTest(unittest.TestCase):
    def test_duration_covers_the_visible_cue(self):
        self.assertEqual(preview_fx.frames_for(0.95), 29)
        self.assertEqual(preview_fx.frames_for(0.5), 15)
        self.assertEqual(preview_fx.frames_for(1.87), 57)
        self.assertEqual(preview_fx.classify("Heart"), "bubble")
        self.assertEqual(preview_fx.classify("hophop"), "action")
        with self.assertRaises(SystemExit):
            preview_fx.classify("nope")

    def test_still_defaults_to_the_middle_frame(self):
        self.assertEqual(preview_fx.choose_frame(29, None), 14)
        self.assertEqual(preview_fx.choose_frame(29, 3), 3)
        with self.assertRaises(SystemExit):
            preview_fx.choose_frame(29, 29)

    def test_bubble_preview_keeps_preset_placement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_character(root, spine=True)
            raws = root / "raws"
            with patch.object(lib, "ROOT", root), patch.object(lib, "CHARACTERS", root / "data" / "characters"), \
                    patch("sprite_coordinates.face_centre", return_value={"x": 0, "y": 150}):
                scene = preview_fx.build_preview("demo", "Heart", raws, mute=True)
            cue = scene["shots"][0]["characters"][0]["bubbles"][0]
            self.assertEqual(set(cue), {"name", "startFrame", "sound", "images"})
            self.assertEqual(cue["name"], "Heart")
            self.assertEqual(cue["startFrame"], 0)
            self.assertFalse(cue["sound"])
            self.assertEqual(scene["episode"]["durationInFrames"], 29)
            self.assertEqual(scene["shots"][0]["characters"][0]["entrance"], "none")
            self.assertIsNone(scene["shots"][0]["scene"])
            self.assertIsNotNone(scene["characters"]["demo"]["outfits"]["default"]["spineBounds"])
            self.assertTrue((raws / cue["images"][0]).is_file())

    def test_action_preview_does_not_need_spine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_character(root, spine=False)
            with patch.object(lib, "ROOT", root), patch.object(lib, "CHARACTERS", root / "data" / "characters"):
                scene = preview_fx.build_preview("demo", "hophop", root / "raws")
            character = scene["shots"][0]["characters"][0]
            self.assertEqual(character["actions"], [{"name": "hophop", "startFrame": 0}])
            self.assertEqual(character["bubbles"], [])
            self.assertIsNone(scene["characters"]["demo"]["outfits"]["default"]["spineBounds"])
            self.assertEqual(scene["episode"]["durationInFrames"], 15)

    def test_scene_background_is_copied_into_the_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_character(root, spine=False)
            image = root / "data" / "scenes" / "club" / "room.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"jpeg")
            lib.write_json(
                image.parent / "scene.yaml",
                {
                    "schema_version": 1,
                    "id": "club",
                    "name": "活动室",
                    "renderer": "image-stage",
                    "default_variant": "afternoon",
                    "image": "room.jpg",
                    "palette": {"ink": "#111111"},
                    "variants": {"afternoon": {"label": "午后", "lighting": "day"}},
                },
            )
            with patch.object(lib, "ROOT", root), \
                    patch.object(lib, "CHARACTERS", root / "data" / "characters"), \
                    patch.object(lib, "SCENES", root / "data" / "scenes"):
                scene = preview_fx.build_preview("demo", "jump", root / "raws", scene_id="club")
            stage = scene["shots"][0]["scene"]
            self.assertEqual(stage["renderer"], "image-stage")
            self.assertEqual(stage["variant"], "afternoon")
            self.assertEqual(stage["lighting"], "day")
            self.assertTrue((root / "raws" / stage["image"]).is_file())

    def test_episode_shot_reuses_room_and_standing_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "003"
            episode.mkdir()
            lib.write_json(
                episode / "storyboard.json",
                {
                    "shots": [
                        {
                            "id": "S2",
                            "scene": {"id": "club", "variant": "lamp"},
                            "characters": [
                                {
                                    "id": "demo",
                                    "outfit": "default",
                                    "x": 0.62,
                                    "bottom": -0.2,
                                    "height": 1.1,
                                    "facing": "left",
                                    "emotion": "excited",
                                }
                            ],
                        }
                    ]
                },
            )
            placed = preview_fx.placement_from_shot(str(episode), "S2", "demo")
            self.assertEqual(placed["scene_id"], "club")
            self.assertEqual(placed["variant"], "lamp")
            self.assertEqual(placed["x"], 0.62)
            self.assertEqual(placed["facing"], "left")
            self.assertEqual(placed["emotion"], "excited")

    def test_bubble_without_spine_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_character(root, spine=False)
            with patch.object(lib, "ROOT", root), patch.object(lib, "CHARACTERS", root / "data" / "characters"):
                with self.assertRaises(SystemExit):
                    preview_fx.build_preview("demo", "Heart", root / "raws", mute=True)


if __name__ == "__main__":
    unittest.main()
