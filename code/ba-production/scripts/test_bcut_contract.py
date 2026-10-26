"""Exercise a third template through the complete generic export, without BA rules."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import wave

from PIL import Image

import bcut_processor
import export_bcut
from bcut_events import AudioEvent
from image_layout import ImageElement, ImagePose, pose_at, render_images


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raws = self.root / "raws"
        self.assets = self.root / "assets"
        self.raws.mkdir()
        self.assets.mkdir()
        Image.new("RGBA", (4, 4), "red").save(self.raws / "sprite.png")
        with wave.open(str(self.raws / "tone.wav"), "wb") as audio:
            audio.setparams((1, 2, 48000, 0, "NONE", ""))
            audio.writeframes(b"\0\0" * 48000)
        self.scene = {"episode": {"template": "third", "title": "Contract", "width": 40,
                                  "height": 20, "fps": 30, "durationInFrames": 30}, "shots": [{"from": 0}]}

    def test_moving_images_hold_endpoints_and_preserve_transparent_edges(self):
        element = ImageElement("sprite.png", 0, 12, "sprite", (
            ImagePose(2, 4, 10, 4, 4), ImagePose(10, 20, 10, 4, 4, .5)))
        self.assertEqual(pose_at(element, 0).x, 4)
        self.assertEqual(pose_at(element, 6).x, 12)
        self.assertEqual(pose_at(element, 11).x, 20)
        spans = render_images(self.scene, self.raws, self.assets, [element])
        for frame, x, alpha in [(0, 2, 255), (6, 10, 191), (11, 18, 128)]:
            span = next(s for s in spans if s["startFrame"] <= frame < s["endFrame"])
            with Image.open(self.assets / span["name"]) as image:
                self.assertEqual(image.getchannel("A").getbbox(), (x, 8, x+4, 12))
                self.assertEqual(image.getpixel((x, 8))[3], alpha)

    def test_complete_third_template_exports_without_registry_or_ba_fields(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        folder = self.root / "templates" / "third"
        folder.mkdir(parents=True)
        (folder / "bcut.py").write_text(
            'from image_layout import ImageElement, ImagePose\n'
            'from bcut_events import AudioEvent\n'
            'TEXT_BELOW = set()\n'
            'def images(scene):\n'
            '    return [ImageElement("sprite.png",0,30,"moving",(ImagePose(0,4,10,4,4),ImagePose(29,30,10,4,4)))]\n'
            'def audio_events(scene, **kwargs):\n'
            '    return [AudioEvent("tone.wav",3,27,volume=.25,fade_in=3,fade_out=3)]\n')
        processor = type("TextProcessor", (), {"layout": lambda *a, **kw: []})()
        output = self.root / "bundle"
        output.mkdir()
        with patch.object(bcut_processor, "__file__", str(scripts / "bcut_processor.py")), patch(
                "text_layout.load_processor", return_value=processor):
            export_bcut.build(self.scene, self.raws, output)
        draft = json.loads((output / "draft.bjson").read_text())
        timeline = draft["timelineWidget"]["timeline"]
        clips = timeline["videoTracks"][0]["clips"]
        self.assertEqual(len(timeline["videoTracks"]), 1)
        self.assertEqual((clips[0]["inPoint"], clips[-1]["outPoint"]), (0, 1000))
        self.assertGreater(len(clips), 1)
        clip = timeline["audioTracks"][0]["audioClips"][0]
        self.assertEqual((clip["inPoint"],clip["outPoint"],clip["fadeIn"],clip["fadeOut"]), (100,900,100,100))

    def test_reject_invalid_images_audio_and_missing_processors(self):
        pose = ImagePose(0, 5, 5, 4, 4)
        for poses in [(pose, pose), (ImagePose(0, 0, 0, -1, 1),),
                      (ImagePose(0, float("nan"), 0, 1, 1),)]:
            with self.assertRaises(ValueError):
                ImageElement("sprite.png", 0, 20, "x", poses).validate(30)
        with self.assertRaises(ValueError):
            render_images(self.scene, self.raws, self.assets,
                          [ImageElement("../sprite.png", 0, 20, "x", (pose,))])
        for event in [AudioEvent("tone.wav", 0, 40), AudioEvent("tone.wav", 0, 2, volume=-1),
                      AudioEvent("tone.wav", 0, 2, trim_in=-1)]:
            with self.assertRaises(ValueError):
                event.validate(30)
        self.scene["episode"]["template"] = "../official"
        with self.assertRaises(ValueError):
            bcut_processor.load_processor(self.scene)


if __name__ == "__main__":
    unittest.main()
