"""Timing math for transitions: padding, overlap and shot-relative fields."""
import sys
import tempfile
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lib
import prepare

TIMING = {
    "intro_frames": 60,
    "lead_in_frames": 18,
    "tail_frames": 14,
    "min_line_frames": 48,
    "shot_cut_lead_frames": 15,
    "shot_tail_frames": 18,
    "outro_frames": 24,
}


def line(lid: str, start: int, frames: int = 100) -> dict:
    return {
        "id": lid,
        "speaker": "saiba-momoi",
        "outfit": "default",
        "emotion": "default",
        "text": lid,
        "start": start,
        "frames": frames,
        "seconds": frames / 30,
        "audio": f"audio/{lid}.mp3",
        "tts": {"provider": "reused"},
    }


def board(count: int, backgrounds: list[str] | None = None) -> list[dict]:
    backgrounds = backgrounds or ["#fff"] * count
    return [
        {
            "id": f"S{index + 1}",
            "background": backgrounds[index],
            "lines": [f"L{index + 1}"],
        }
        for index in range(count)
    ]


def build(count: int, transitions: dict | None, backgrounds: list[str] | None = None):
    timed = [line(f"L{index + 1}", index * 100) for index in range(count)]
    return prepare.build_shots(
        board(count, backgrounds),
        timed,
        TIMING,
        {},
        {"saiba-momoi": "default"},
        transitions,
    )


class ParseTransitionTest(unittest.TestCase):
    def test_every_bubble_name_survives_prepare(self):
        for name in prepare.BUBBLE_PRESETS:
            with self.subTest(name=name):
                raw = board(1)
                raw[0]["characters"] = [{"id": "saiba-momoi", "bubbles": [{"name": name, "startFrame": 10}]}]
                shots, _, _ = prepare.build_shots(raw, [line("L1", 0)], TIMING, {}, {"saiba-momoi": "default"})
                self.assertEqual(shots[0]["characters"][0]["bubbles"], [{"name": name, "startFrame": 10, "sound": True}])

    def test_bubble_snapshot_copies_media_and_mute_needs_no_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "data/effects/ba"
            images.mkdir(parents=True)
            for name in ["Emoticon_Balloon_N.png", "Emoticon_Shy.png"]:
                (images / name).write_bytes(b"test-png")
            cue = {"name": "Shy", "startFrame": 0, "sound": False}
            shots = [{"characters": [{"bubbles": [cue]}]}]
            with patch.object(lib, "ROOT", root):
                prepare.snapshot_bubbles(shots, root / "raws")
                self.assertEqual((root / "raws" / cue["images"][1]).read_bytes(), b"test-png")
                self.assertNotIn("audio", cue)
                cue["sound"] = True
                with self.assertRaises(SystemExit):
                    prepare.snapshot_bubbles(shots, root / "raws")

    def test_defaults_fill_gaps(self):
        parsed = lib.parse_transition({"type": "slide"}, {"durationInFrames": 20})
        self.assertEqual(parsed, {"type": "slide", "durationInFrames": 20})

    def test_none_is_a_hard_cut(self):
        self.assertIsNone(lib.parse_transition("none"))
        self.assertIsNone(lib.parse_transition({"type": "none", "durationInFrames": 12}))

    def test_direction_is_checked_per_type(self):
        self.assertEqual(lib.parse_transition("wipe", {"direction": "from-top-left"})["direction"], "from-top-left")
        with self.assertRaises(ValueError):
            lib.parse_transition({"type": "wipe", "direction": "sideways"})
        with self.assertRaises(ValueError):
            lib.parse_transition({"type": "fade", "direction": "from-left"})
        with self.assertRaises(ValueError):
            lib.parse_transition({"type": "spin"})

    def test_duration_must_be_positive(self):
        with self.assertRaises(ValueError):
            lib.parse_transition({"type": "fade", "durationInFrames": 0})


class CutResolutionTest(unittest.TestCase):
    keys = [("background", "#fff"), ("background", "#fff"), ("background", "#000")]

    def resolve(self, index, raw, cfg):
        return prepare.resolve_transition(index, raw, self.keys, cfg)

    def test_no_config_means_hard_cuts(self):
        self.assertIsNone(self.resolve(1, {"id": "S2"}, None))

    def test_scene_change_only(self):
        cfg = {"on": "scene-change", "type": "fade", "durationInFrames": 12}
        self.assertIsNone(self.resolve(1, {"id": "S2"}, cfg))
        self.assertEqual(self.resolve(2, {"id": "S3"}, cfg)["type"], "fade")

    def test_every_cut(self):
        cfg = {"on": "every-cut", "type": "wipe", "durationInFrames": 8}
        self.assertEqual(self.resolve(1, {"id": "S2"}, cfg)["durationInFrames"], 8)

    def test_explicit_beats_episode_default(self):
        cfg = {"on": "none", "type": "fade", "durationInFrames": 12}
        explicit = self.resolve(1, {"id": "S2", "transition": {"type": "iris"}}, cfg)
        self.assertEqual(explicit, {"type": "iris", "durationInFrames": 12})
        self.assertIsNone(self.resolve(2, {"id": "S3", "transition": "none"}, cfg))

    def test_explicit_type_inherits_only_the_duration(self):
        cfg = {
            "on": "scene-change",
            "type": "slide",
            "durationInFrames": 20,
            "direction": "from-left",
        }
        shot = {"id": "S2", "transition": {"type": "fade"}}
        self.assertEqual(self.resolve(1, shot, cfg), {"type": "fade", "durationInFrames": 20})

    def test_explicit_without_type_inherits_the_episode_presentation(self):
        cfg = {"on": "every-cut", "type": "wipe", "durationInFrames": 20}
        shot = {"id": "S2", "transition": {"direction": "from-top-left"}}
        self.assertEqual(
            self.resolve(1, shot, cfg),
            {"type": "wipe", "durationInFrames": 20, "direction": "from-top-left"},
        )

    def test_first_shot_cannot_transition(self):
        with self.assertRaises(SystemExit):
            self.resolve(0, {"id": "S1", "transition": "fade"}, None)


class ShotLayoutTest(unittest.TestCase):
    def test_every_cut_inserts_padding_and_overlap(self):
        cfg = {"on": "every-cut", "type": "fade", "durationInFrames": 10}
        shots, total, shifts = build(3, cfg)

        # Absolute starts follow the TransitionSeries overlap rule.
        self.assertEqual([shot["from"] for shot in shots], [0, 100, 210])
        self.assertEqual([shot["durationInFrames"] for shot in shots], [110, 120, 134])
        self.assertEqual(total, 324 + 20)

        # Dialogue moves right by the accumulated padding, so nothing overlaps.
        self.assertEqual([line["from"] for shot in shots for line in shot["lines"]], [0, 110, 220])
        self.assertEqual(shifts, {"L1": 0, "L2": 10, "L3": 20})

        # Each shot's content starts one transition after its sequence start.
        self.assertEqual(shots[1]["lines"][0]["from"] - shots[1]["from"], 10)
        self.assertEqual(shots[2]["lines"][0]["from"] - shots[2]["from"], 10)

        # Total duration grows by the transitions only.
        self.assertEqual(total - 324, 20)

    def test_scene_change_leaves_same_scene_cuts_hard(self):
        cfg = {"on": "scene-change", "type": "fade", "durationInFrames": 12}
        shots, total, _ = build(3, cfg, ["#fff", "#fff", "#000"])
        self.assertIsNone(shots[1]["transition"])
        self.assertEqual(shots[1]["from"], 100)
        self.assertEqual(shots[2]["transition"]["durationInFrames"], 12)
        self.assertEqual(total, 324 + 12)

    def test_shot_relative_fields_skip_the_transition_window(self):
        cfg = {"on": "every-cut", "type": "fade", "durationInFrames": 10}
        timed = [line("L1", 0), line("L2", 100)]
        raw = board(2)
        raw[1]["buttons"] = [{"label": "GO", "pressFrame": 5}]
        raw[1]["choices"] = {
            "options": ["A", "B"],
            "fromFrame": 30,
            "selectFrame": 40,
            "hideFrame": 50,
        }
        raw[1]["characters"] = [
            {"id": "saiba-momoi", "motion": {"startFrame": 0, "endFrame": 60},
             "actions": [{"name": "falldownL", "startFrame": 20}],
             "bubbles": [{"name": "Shy", "startFrame": 30, "sound": False}]}
        ]
        shots, _, _ = prepare.build_shots(
            raw, timed, TIMING, {}, {"saiba-momoi": "default"}, cfg
        )
        self.assertEqual(shots[1]["buttons"][0]["pressFrame"], 15)
        self.assertEqual(shots[1]["choices"]["fromFrame"], 40)
        self.assertEqual(shots[1]["choices"]["selectFrame"], 50)
        self.assertEqual(shots[1]["choices"]["hideFrame"], 60)
        self.assertEqual(shots[1]["characters"][0]["motion"], {"startFrame": 10, "endFrame": 70})
        self.assertEqual(shots[1]["characters"][0]["actions"], [{"name": "falldownL", "startFrame": 30}])
        self.assertEqual(shots[1]["characters"][0]["bubbles"], [{"name": "Shy", "startFrame": 40, "sound": False}])

    def test_bubble_at_line_is_content_relative(self):
        raw = board(1)
        raw[0]["characters"] = [{
            "id": "saiba-momoi",
            "bubbles": [{"name": "Heart", "atLine": "L1", "offsetFrames": 6, "x": 12, "scale": 2, "duration": 90}],
        }]
        shots, _, _ = prepare.build_shots(raw, [line("L1", 0, frames=40)], TIMING, {}, {"saiba-momoi": "default"})
        bubble = shots[0]["characters"][0]["bubbles"][0]
        self.assertEqual(bubble, {"name": "Heart", "startFrame": 6, "sound": True})

    def test_bubble_at_line_matches_line_end_plus_lead(self):
        cfg = {"on": "every-cut", "type": "fade", "durationInFrames": 10}
        timed = [line("L1", 0), line("L2", 100, frames=40)]
        raw = board(2)
        raw[1]["characters"] = [{
            "id": "saiba-momoi",
            "bubbles": [{"name": "Heart", "atLine": "L2", "offsetFrames": 46}],
        }]
        shots, _, _ = prepare.build_shots(raw, timed, TIMING, {}, {"saiba-momoi": "default"}, cfg)
        line_item = shots[1]["lines"][0]
        expected = line_item["from"] + line_item["durationInFrames"] - shots[1]["from"] + 6
        self.assertEqual(shots[1]["characters"][0]["bubbles"][0]["startFrame"], expected)

    def test_bubble_at_line_rejects_unknown_line_and_manual_mix(self):
        raw = board(1)
        raw[0]["characters"] = [{"id": "saiba-momoi", "bubbles": [{"name": "Heart", "atLine": "missing"}]}]
        with self.assertRaises(SystemExit):
            prepare.build_shots(raw, [line("L1", 0)], TIMING, {}, {"saiba-momoi": "default"})
        raw[0]["characters"] = [{
            "id": "saiba-momoi",
            "bubbles": [{"name": "Heart", "atLine": "L1", "startFrame": 4}],
        }]
        with self.assertRaises(SystemExit):
            prepare.build_shots(raw, [line("L1", 0)], TIMING, {}, {"saiba-momoi": "default"})
        raw[0]["characters"] = [{
            "id": "saiba-momoi",
            "bubbles": [{"name": "Heart", "startFrame": 4, "offsetFrames": 2}],
        }]
        with self.assertRaises(SystemExit):
            prepare.build_shots(raw, [line("L1", 0)], TIMING, {}, {"saiba-momoi": "default"})

    def test_invalid_bubbles_are_rejected(self):
        for cue in [
            {"name": "Invalid", "startFrame": 0},
            {"name": "Shy", "startFrame": -1},
            {"name": "Shy", "startFrame": True},
            {"name": "Shy", "startFrame": 0, "sound": "false"},
        ]:
            with self.subTest(cue=cue), self.assertRaises(SystemExit):
                raw = board(1)
                raw[0]["characters"] = [{"id": "saiba-momoi", "bubbles": [cue]}]
                prepare.build_shots(raw, [line("L1", 0)], TIMING, {}, {"saiba-momoi": "default"})

    def test_invalid_actions_are_rejected(self):
        for cue in [
            {"name": "typo", "startFrame": 0},
            {"name": "jump", "startFrame": -1},
            {"name": "jump", "startFrame": 1000},
            {"name": "jump", "startFrame": 0.5},
            {"name": "jump", "startFrame": True},
        ]:
            with self.subTest(cue=cue), self.assertRaises(SystemExit):
                raw = board(1)
                raw[0]["characters"] = [{"id": "saiba-momoi", "actions": [cue]}]
                prepare.build_shots(raw, [line("L1", 0)], TIMING, {}, {"saiba-momoi": "default"})

    def test_transition_longer_than_a_shot_is_rejected(self):
        cfg = {"on": "every-cut", "type": "fade", "durationInFrames": 120}
        with self.assertRaises(SystemExit):
            build(2, cfg)


class IntroHoldTest(unittest.TestCase):
    def test_missing_intro_reserves_nothing(self):
        self.assertEqual(lib.intro_hold_frames({}), 0)
        self.assertEqual(lib.intro_hold_frames({"timing": TIMING}, TIMING), 0)

    def test_duration_overrides_the_timing_default(self):
        config = {"intro": {"durationInFrames": 90, "title": "夏日补丁"}}
        self.assertEqual(lib.intro_hold_frames(config, TIMING), 90)

    def test_omitted_duration_uses_timing_intro_frames(self):
        self.assertEqual(lib.intro_hold_frames({"intro": {"title": "夏日补丁"}}, TIMING), 60)

    def test_bad_intro_is_rejected(self):
        with self.assertRaises(ValueError):
            lib.intro_hold_frames({"intro": {"durationInFrames": -1}}, TIMING)
        with self.assertRaises(ValueError):
            lib.intro_hold_frames({"intro": "Episode 1"}, TIMING)
        with self.assertRaises(ValueError):
            lib.intro_hold_frames({"intro": {"durationInFrames": True}}, TIMING)

    @patch("prepare.shutil.copy2")
    @patch("prepare.lib.probe_duration", return_value=1.0)
    @patch(
        "prepare.voice.synthesize_line",
        return_value={"provider": "reused", "voice_id": "", "model": "", "speed": 1.0, "fallback": False},
    )
    def test_first_line_starts_after_the_card_only_when_intro_exists(self, _synth, _probe, _copy):
        script = [{"id": "L1", "speaker": "saiba-momoi", "emotion": "default", "text": "老师"}]
        characters = {"saiba-momoi": {"default_outfit": "default", "voice": {}}}
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            without, _, _ = prepare.build_timing(
                script, characters, {"L1": "default"}, episode, 30, TIMING, False, 30, False, intro_hold=0
            )
            with_card, _, _ = prepare.build_timing(
                script, characters, {"L1": "default"}, episode, 30, TIMING, False, 30, False, intro_hold=40
            )
        self.assertEqual(without[0]["start"], TIMING["lead_in_frames"])
        self.assertEqual(with_card[0]["start"], 40 + TIMING["lead_in_frames"])


if __name__ == "__main__":
    unittest.main()
