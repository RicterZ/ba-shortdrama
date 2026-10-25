"""Offline format/portability tests; these do not validate the Bcut application."""
import copy
import json
import tempfile
import unittest
import wave
from pathlib import Path

from PIL import Image

import export_bcut
import install_bcut


class BcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raws = self.root / "raws"
        self.raws.mkdir()
        Image.new("RGB", (200, 100), "blue").save(self.raws / "bg.png")
        Image.new("RGBA", (20, 60), "red").save(self.raws / "sprite.png")
        with wave.open(str(self.raws / "voice.wav"), "wb") as audio:
            audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\0\0" * 48000)
        self.scene = {
            "episode": {"title": "Test", "width": 200, "height": 100,
                        "fps": 30, "durationInFrames": 90, "template": "official"},
            "characters": {"c": {"default_outfit": "a", "outfits": {"a": {
                "sprites": {"default": "sprite.png"}}}}},
            "shots": [{"id": "s", "from": 0, "durationInFrames": 90,
                       "scene": {"image": "bg.png"},
                       "characters": [{"id": "c", "x": .5}],
                       "lines": [{"from": 10, "durationInFrames": 40, "speaker": "c",
                                  "text": "Hello", "audio": "voice.wav"}]}],
            "bgm": {"src": "voice.wav", "loop": True, "volume": .5},
        }
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()

    def build(self):
        export_bcut.build(self.scene, self.raws, self.bundle)
        return json.loads((self.bundle / "draft.bjson").read_text())

    def test_layers_timing_and_loop(self):
        draft = self.build()
        tl = draft["timelineWidget"]["timeline"]
        self.assertEqual(len(tl["videoTracks"]), 2)
        pose = tl["videoTracks"][1]["clips"]
        self.assertEqual([(c["inPoint"], c["outPoint"]) for c in pose], [(0, 3000)])
        self.assertEqual(tl["captionTracks"][0]["captions"][0]["inPoint"], 333)
        self.assertTrue((self.bundle / "cover.jpg").is_file())
        voice = tl["audioTracks"][0]["audioClips"][0]
        self.assertEqual((voice["inPoint"], voice["outPoint"]), (333, 1333))
        music = tl["audioTracks"][1]["audioClips"]
        self.assertEqual([(c["inPoint"], c["outPoint"]) for c in music],
                         [(0, 1000), (1000, 2000), (2000, 3000)])
        self.assertAlmostEqual(music[0]["fxs"][0]["gainValue"], -6.0206, places=4)

    def test_install_preserves_index_and_relocates(self):
        self.build()
        root = self.root / "Drafts"
        root.mkdir()
        index = root / "draftInfo.json"
        original = b'{"extra": 42, "draftInfos": [{"id": "old", "name": "Keep"}]}'
        index.write_bytes(original)
        first = install_bcut.install(self.bundle, root)
        second = install_bcut.install(self.bundle, root)
        self.assertNotEqual(first, second)
        info = json.loads(index.read_text())
        self.assertEqual(info["extra"], 42)
        self.assertEqual(len(info["draftInfos"]), 3)
        self.assertEqual(info["draftInfos"][0]["name"], "Keep")
        self.assertEqual(info["draftInfos"][1]["duration"], 3000000)
        self.assertIn(original, [p.read_bytes() for p in root.glob("*.bak")])
        data = json.loads(next(first.glob("*.bjson")).read_text())
        self.assertNotIn("__BA_ASSETS__", json.dumps(data))
        for tr in data["timelineWidget"]["timeline"]["videoTracks"]:
            for clip in tr["clips"]:
                self.assertTrue(Path(clip["sourcePath"]).is_file())

    def test_bad_index_unchanged(self):
        self.build()
        root = self.root / "Drafts"
        root.mkdir()
        index = root / "draftInfo.json"
        index.write_text("broken")
        with self.assertRaises(ValueError):
            install_bcut.install(self.bundle, root)
        self.assertEqual(index.read_text(), "broken")
        self.assertEqual(list(root.iterdir()), [index])

    def test_lock_stops_parallel_install(self):
        self.build()
        root = self.root / "Drafts"
        root.mkdir()
        (root / ".ba-import.lock").touch()
        with self.assertRaises(FileExistsError):
            install_bcut.install(self.bundle, root)

    def test_missing_asset_fails_before_install_changes(self):
        self.build()
        for path in (self.bundle / "assets").iterdir():
            path.unlink()
        root = self.root / "Drafts"
        with self.assertRaises(ValueError):
            install_bcut.install(self.bundle, root)
        self.assertEqual(list(root.iterdir()), [])

    def test_expression_returns_to_standing_face(self):
        self.scene["shots"][0]["characters"][0]["emotion"] = "default"
        self.scene["shots"][0]["lines"][0]["emotion"] = "happy"
        self.scene["shots"][0]["characters"][0]["emotionCues"] = [
            {"emotion": "shy", "startFrame": 20}]
        draft = self.build()
        clips = draft["timelineWidget"]["timeline"]["videoTracks"][1]["clips"]
        self.assertEqual(
            [(c["inPoint"], c["outPoint"], c["assetInfo"]["displayName"]) for c in clips],
            [(0, 333, "c default"), (333, 667, "c happy"), (667, 3000, "c shy")])

    def test_hold_emotion_stays_after_the_line(self):
        self.scene["shots"][0]["characters"][0]["emotion"] = "default"
        self.scene["shots"][0]["characters"][0]["holdEmotion"] = True
        self.scene["shots"][0]["lines"][0]["emotion"] = "happy"
        draft = self.build()
        clips = draft["timelineWidget"]["timeline"]["videoTracks"][1]["clips"]
        self.assertEqual(
            [(c["inPoint"], c["outPoint"], c["assetInfo"]["displayName"]) for c in clips],
            [(0, 333, "c default"), (333, 3000, "c happy")])

    def test_overlapping_shots_cut_instead_of_stacking(self):
        self.scene["episode"]["durationInFrames"] = 120
        self.scene["shots"][0]["durationInFrames"] = 100
        self.scene["shots"].append({
            "id": "t", "from": 90, "durationInFrames": 30,
            "scene": {"image": "bg.png"},
            "characters": [{"id": "c", "x": .2, "emotion": "default"}],
            "lines": [],
        })
        draft = self.build()
        tracks = draft["timelineWidget"]["timeline"]["videoTracks"]
        spans = lambda track: [(c["inPoint"], c["outPoint"]) for c in track["clips"]]
        self.assertEqual(spans(tracks[0]), [(0, 3000), (3000, 4000)])
        self.assertEqual(spans(tracks[1]), [(0, 3000), (3000, 4000)])

    def test_reject_unsafe_asset_and_unsupported_template(self):
        bad = copy.deepcopy(self.scene)
        bad["episode"]["template"] = "blue-archive"
        with self.assertRaisesRegex(ValueError, "official"):
            export_bcut.build(bad, self.raws, self.bundle)
        bad = copy.deepcopy(self.scene)
        bad["shots"][0]["scene"]["image"] = "../outside.png"
        with self.assertRaises(ValueError):
            export_bcut.build(bad, self.raws, self.bundle)

    def test_spy_places_text_and_splits_muted_music(self):
        self.scene["episode"]["template"] = "who-is-the-spy"
        self.scene["characters"]["c"]["color"] = "#ff8800"
        self.scene["shots"][0]["characters"][0]["x"] = 0.1
        self.scene["shots"][0]["characters"][0]["label"] = {"text": "西瓜", "tone": "normal"}
        self.scene["shots"][0]["systemVoice"] = "voice.wav"
        self.scene["shots"][0]["voteTags"] = [{"speaker": "c", "text": "凯伊"}]
        self.scene["shots"][0]["lines"][0]["text"] = "外面有条纹。"
        self.scene["shots"][0]["lines"].append({
            "from": 50, "durationInFrames": 20, "speaker": "c", "kind": "thought",
            "text": "好像不是。", "audio": "voice.wav",
        })
        self.scene["bgm"]["muteRanges"] = [{"from": 30, "durationInFrames": 30}]
        self.scene["bgm"]["cues"] = [{
            "from": 30, "durationInFrames": 30, "src": "voice.wav", "volume": 0.5, "loop": False,
        }]
        draft = self.build()
        tl = draft["timelineWidget"]["timeline"]
        speech, thought = tl["captionTracks"][0]["captions"]
        self.assertEqual(speech["captionText"], "外面有条纹")
        self.assertEqual(thought["captionText"], "好像不是")
        self.assertLess(speech["transY"], thought["transY"])
        self.assertGreater(speech["scaleX"], thought["scaleX"])
        label = tl["captionTracks"][1]["captions"][0]
        self.assertEqual((label["captionText"], label["transX"] < 0, label["transY"] > 0.5),
                         ("西瓜", True, True))
        vote = tl["captionTracks"][2]["captions"][0]
        self.assertEqual((vote["captionText"], vote["inPoint"], vote["outPoint"]), ("凯伊", 2333, 3000))
        music = tl["audioTracks"][1]["audioClips"]
        self.assertEqual([(c["inPoint"], c["outPoint"]) for c in music], [(0, 1000), (2000, 3000)])
        self.assertEqual([(c["inPoint"], c["outPoint"]) for c in tl["audioTracks"][3]["audioClips"]],
                         [(1000, 2000)])


if __name__ == "__main__":
    unittest.main()
