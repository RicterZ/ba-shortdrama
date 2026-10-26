"""Offline format/portability tests; these do not validate the Bcut application."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
import wave
from pathlib import Path

from PIL import Image

import export_bcut
import install_bcut
import text_layout
from render_bcut_layers import effect_audio_events, render_layers, layer_frame_ranges, render_jobs, default_layers


class BcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # A format fixture, not a real font: installation only resolves its path.
        self.font = self.root / "test-font.ttf"
        self.font.write_bytes(b"font-path-fixture")
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

    def install(self, root):
        return install_bcut.install(self.bundle, root, font_path=self.font)

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

    def test_image_clips_have_no_undefined_crop(self):
        draft = self.build()
        tracks = draft["timelineWidget"]["timeline"]["videoTracks"]
        for track in tracks:
            for clip in track["clips"]:
                self.assertFalse(any(fx.get("businessType") == 2 for fx in clip["fxs"]))
                self.assertEqual(clip["propertyFxList"], [])

    def test_caption_indices_stack_above_every_video_track(self):
        self.scene["episode"]["template"] = "who-is-the-spy"
        self.scene["shots"][0]["characters"][0]["label"] = {"text": "Word"}
        self.scene["shots"][0]["voteTags"] = [{"speaker": "c", "text": "Vote"}]
        timeline = self.build()["timelineWidget"]["timeline"]
        video_indices = [track["index"] for track in timeline["videoTracks"]]
        caption_indices = [track["index"] for track in timeline["captionTracks"]]
        self.assertEqual(len(set(video_indices + caption_indices)),
                         len(video_indices) + len(caption_indices))
        self.assertGreater(min(caption_indices), max(video_indices))

    def test_effect_sounds_match_intro_visibility_and_clip_boundaries(self):
        self.scene["intro"] = {"durationInFrames": 20}
        self.scene["ui"] = {"sfx": {"click": "click.wav", "hover": "hover.wav",
                                     "select": "select.wav"}}
        shot = self.scene["shots"][0]
        shot["characters"][0]["bubbles"] = [
            {"name": "Shy", "startFrame": 5, "audio": "bubble.wav"},
            {"name": "Dot", "startFrame": 10, "audio": "disabled.wav", "sound": False}]
        shot["buttons"] = [{"pressFrame": 18}]
        shot["choices"] = {"options": ["yes"], "fromFrame": 10,
                           "selectFrame": 30, "hideFrame": 35}
        expected = [("click.wav", 22, 32, 0, .3),
                    ("bubble.wav", 5, 90, 0, .5),
                    ("click.wav", 20, 30, 2, .55),
                    ("select.wav", 30, 35, 0, .65)]
        for template in ("official", "who-is-the-spy"):
            with self.subTest(template=template):
                self.scene["episode"]["template"] = template
                events = effect_audio_events(self.scene)
                self.assertEqual([(event["src"], event["startFrame"], event["endFrame"],
                                   event["trimInFrames"], event["volume"]) for event in events], expected)

    def test_editable_spy_omits_rendered_text_layers(self):
        self.scene["episode"]["template"] = "who-is-the-spy"
        layers = default_layers(self.scene, editable_captions=True)
        self.assertIn("dialogue-ba", layers)
        self.assertIn("buttons", layers)
        self.assertFalse(set(layers) & {"word-labels", "votes", "thought", "meme"})

    def test_visual_layers_match_css_stacking_contexts(self):
        layers = default_layers(self.scene)
        self.assertLess(layers.index("dialogue-full"), layers.index("choices"))
        self.assertLess(layers.index("choices"), layers.index("buttons"))
        self.assertLess(layers.index("buttons"), layers.index("chrome"))
        self.scene["episode"]["template"] = "who-is-the-spy"
        layers = default_layers(self.scene)
        self.assertLess(layers.index("word-labels"), layers.index("choices"))
        self.assertLess(layers.index("votes"), layers.index("buttons"))
        self.assertLess(layers.index("buttons"), layers.index("thought"))
        self.assertLess(layers.index("meme"), layers.index("chrome"))

    def test_template_pixel_layout_maps_to_native_text(self):
        element = text_layout.TextElement("Custom layout", 15, 45,
            center_x=50, center_y=25, font_size=8.4, track=2,
            color="#ff0000", alignment=0, draw_outline=False)
        with patch("text_layout.text_elements", return_value=[element]):
            export_bcut.build(self.scene, self.raws, self.bundle)
        draft = json.loads((self.bundle / "draft.bjson").read_text())
        clip = draft["timelineWidget"]["timeline"]["captionTracks"][0]["captions"][0]
        self.assertEqual((clip["captionText"], clip["inPoint"], clip["outPoint"]),
                         ("Custom layout", 500, 1500))
        self.assertEqual((clip["transX"], clip["transY"], clip["scaleX"]), (-.5, .5, 1.12))
        self.assertEqual(clip["textColor"], {"r": 1, "g": 0, "b": 0, "a": 1})
        self.assertFalse(clip["drawOutline"])
        self.assertEqual(clip["textAlignment"], 0)

    def test_new_template_text_processor_needs_no_registry_entry(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        processor = self.root / "templates" / "third-template"
        processor.mkdir(parents=True)
        (processor / "text_layout.py").write_text(
            'from text_layout import TextElement\n'
            'def layout(scene, **kwargs):\n'
            '    yield TextElement("Third", 0, 10, center_x=12, font_size=8)\n')
        self.scene["episode"]["template"] = "third-template"
        with patch.object(text_layout, "__file__", str(scripts / "text_layout.py")):
            elements = text_layout.text_elements(self.scene)
        self.assertEqual(elements[0].text, "Third")
        self.assertEqual(elements[0].center_x, 12)

    def test_invalid_template_text_fails_before_draft_is_written(self):
        for values in ({"font_size": 0}, {"center_x": float("nan")},
                       {"rotation": float("inf")}, {"start": -1}, {"end": 0}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                text_layout.TextElement(**{"text": "X", "start": 0, "end": 10, **values}).validate()
        self.scene["episode"]["template"] = "../official"
        with self.assertRaises(ValueError):
            text_layout.text_elements(self.scene)

    def test_official_processor_owns_dialogue_layout_and_prompt_gaps(self):
        self.scene["intro"] = {"durationInFrames": 20}
        self.scene["shots"][0]["choices"] = {"prompt": "Pick one"}
        elements = text_layout.text_elements(self.scene, visual_layers=True, editable_captions=True)
        self.assertEqual([(e.text, e.start, e.end) for e in elements],
                         [("Hello", 20, 50), ("Pick one", 50, 90)])
        self.assertAlmostEqual(elements[0].center_y, 100 * (.76 + .038 * 1.12 / 2))
        self.assertAlmostEqual(elements[0].font_size, 3.192)
        self.assertFalse(elements[0].draw_outline)
        self.assertEqual(text_layout.text_elements(self.scene, visual_layers=True), [])

    def test_main_track_cannot_ripple_intro_and_transition_gaps(self):
        def rendered(scene, raws, assets, **kwargs):
            Image.new("RGB", (200, 100), "blue").save(assets / "background.png")
            return [{"layer": "background", "name": "background.png",
                     "label": "background", "startFrame": start, "endFrame": end}
                    for start, end in [(20, 30), (35, 90)]]

        with patch("render_bcut_layers.render_layers", side_effect=rendered), patch(
                "compact_bcut_layers.compact_layers", side_effect=lambda spans, *_: spans):
            export_bcut.build(self.scene, self.raws, self.bundle, visual_layers=True)
        draft = json.loads((self.bundle / "draft.bjson").read_text())
        tracks = draft["timelineWidget"]["timeline"]["videoTracks"]
        self.assertEqual([(c["inPoint"], c["outPoint"]) for c in tracks[0]["clips"]],
                         [(0, 3000)])
        self.assertEqual([(c["inPoint"], c["outPoint"]) for c in tracks[1]["clips"]],
                         [(666, 1000), (1166, 3000)])

    def test_render_ranges_skip_only_unmounted_components(self):
        self.scene["intro"] = {"durationInFrames": 20}
        ranges = layer_frame_ranges(self.scene,
            ["background", "character-slot:0", "character-slot:1", "ui", "dialogue-full", "intro"],
            [(30, 35)])
        self.assertEqual(ranges["background"], [[0, 30], [35, 90]])
        self.assertEqual(ranges["character-slot:0"], ranges["background"])
        self.assertEqual(ranges["character-slot:1"], [])
        self.assertEqual(ranges["ui"], [[20, 30], [35, 90]])
        self.assertEqual(ranges["dialogue-full"], [[20, 30], [35, 50]])
        self.assertEqual(ranges["intro"], [[0, 20]])

    def test_spy_thought_mounts_before_intro_and_word_label_leaves_with_motion(self):
        self.scene["episode"].update(template="who-is-the-spy", style={"caption_style": "meme"})
        self.scene["intro"] = {"durationInFrames": 20}
        shot = self.scene["shots"][0]
        shot["lines"][0]["kind"] = "thought"
        shot["characters"][0].update(label={"text": "Word"}, motion={"startFrame": 12})
        ranges = layer_frame_ranges(self.scene, ["ui", "dialogue-full", "labels"])
        self.assertEqual(ranges["ui"], [])
        self.assertEqual(ranges["dialogue-full"], [[10, 50]])
        self.assertEqual(ranges["labels"], [[0, 12]])

    def test_character_state_reuse_keeps_entrance_and_motion_dynamic(self):
        shot = self.scene["shots"][0]
        jobs = render_jobs(self.scene, ["character-slot:0"])
        static = [job for job in jobs if "staticKey" in job]
        self.assertTrue(static)
        self.assertTrue(all(job["start"] >= 30 for job in static))
        self.assertEqual(len({job["staticKey"] for job in static}), 1)
        for field, value in (("motion", {"startFrame": 60}), ("turns", [{"startFrame": 60}]),
                             ("actions", [{"name": "jump"}]), ("bubbles", [{"name": "Shy"}])):
            with self.subTest(field=field):
                shot["characters"][0][field] = value
                self.assertFalse(any("staticKey" in job for job in render_jobs(self.scene, ["character-slot:0"])))
                del shot["characters"][0][field]

    def test_background_reuse_changes_with_speaker_position(self):
        shot = self.scene["shots"][0]
        shot["characters"][0]["x"] = .2
        jobs = render_jobs(self.scene, ["background"])
        self.assertEqual([(job["start"], job["end"]) for job in jobs], [(0, 10), (10, 50), (50, 90)])
        self.assertEqual(jobs[0]["staticKey"], jobs[2]["staticKey"])
        self.assertNotEqual(jobs[0]["staticKey"], jobs[1]["staticKey"])

    def test_install_preserves_index_and_relocates(self):
        self.build()
        root = self.root / "Drafts"
        root.mkdir()
        index = root / "draftInfo.json"
        original = b'{"extra": 42, "draftInfos": [{"id": "old", "name": "Keep"}]}'
        index.write_bytes(original)
        first = self.install(root)
        second = self.install(root)
        self.assertNotEqual(first, second)
        info = json.loads(index.read_text())
        self.assertEqual(info["extra"], 42)
        self.assertEqual(len(info["draftInfos"]), 3)
        self.assertEqual(info["draftInfos"][0]["name"], "Keep")
        self.assertEqual(info["draftInfos"][1]["duration"], 3000000)
        self.assertIn(original, [p.read_bytes() for p in root.glob("*.bak")])
        data = json.loads(next(first.glob("*.bjson")).read_text())
        self.assertNotIn("__BA_ASSETS__", json.dumps(data))
        self.assertNotIn("__BCUT_FONT__", json.dumps(data))
        caption = data["timelineWidget"]["timeline"]["captionTracks"][0]["captions"][0]
        self.assertEqual(caption["defaultFontPath"], self.font.resolve().as_posix())
        self.assertEqual(caption["assetInfo"]["fontSrcPath"], self.font.resolve().as_posix())
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
            self.install(root)
        self.assertEqual(index.read_text(), "broken")
        self.assertEqual(list(root.iterdir()), [index])

    def test_lock_stops_parallel_install(self):
        self.build()
        root = self.root / "Drafts"
        root.mkdir()
        (root / ".ba-import.lock").touch()
        with self.assertRaises(FileExistsError):
            self.install(root)

    def test_missing_asset_fails_before_install_changes(self):
        self.build()
        for path in (self.bundle / "assets").iterdir():
            path.unlink()
        root = self.root / "Drafts"
        with self.assertRaises(ValueError):
            self.install(root)
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
            [(0, 333, "c default"), (333, 666, "c happy"), (666, 3000, "c shy")])
        # At the exact first frame of the new expression, only it is active.
        at = 20 * 1000 / 30
        active = [c for c in clips if c["inPoint"] <= at < c["outPoint"]]
        self.assertEqual([c["assetInfo"]["displayName"] for c in active], ["c shy"])
        for clip in clips:
            self.assertEqual(clip["trimOut"] - clip["trimIn"], clip["outPoint"] - clip["inPoint"])

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

    def test_music_continues_source_after_mute(self):
        with wave.open(str(self.raws / "music.wav"), "wb") as audio:
            audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\0\0" * 48000 * 4)
        self.scene["episode"]["template"] = "who-is-the-spy"
        self.scene["bgm"] = {"src": "music.wav", "loop": True,
                             "muteRanges": [{"from": 30, "durationInFrames": 30}]}
        timeline = self.build()["timelineWidget"]["timeline"]
        clips = timeline["audioTracks"][1]["audioClips"]
        self.assertEqual([(c["inPoint"], c["trimIn"], c["trimOut"]) for c in clips],
                         [(0, 0, 1000), (2000, 2000, 3000)])


if __name__ == "__main__":
    unittest.main()
