import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lib
import prepare
import validate


class ReactionTimingTest(unittest.TestCase):
    def test_silent_and_voiced_lines_keep_audio_and_timing_in_shots(self):
        script = lib.normalize_script([
            {"id": "L1", "speaker": "c", "text": "Silent caption", "silent": True},
            {"id": "L2", "speaker": "c", "text": "Voiced caption"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            (episode / "audio").mkdir()
            (episode / "audio/S1-L2.mp3").write_bytes(b"reused audio")
            with patch.object(prepare.voice, "synthesize_line") as synth, patch.object(
                lib, "probe_duration", return_value=2.0
            ):
                timed, _, _ = prepare.build_timing(
                    script, {"c": {"default_outfit": "default", "voice": {}}}, {},
                    episode, 30, lib.DEFAULT_TIMING, True, 30, False,
                    board=[{"id": "S1", "lines": ["L1", "L2"]}],
                )
            synth.assert_not_called()
            shots, _, _ = prepare.build_shots(
                [{"id": "S1", "lines": ["L1", "L2"]}], timed,
                lib.DEFAULT_TIMING, {}, {"c": "default"},
            )
            silent, voiced = shots[0]["lines"]
            self.assertEqual(silent["audio"], "")
            self.assertEqual(silent["text"], "Silent caption")
            self.assertEqual(silent["durationInFrames"], timed[0]["frames"])
            self.assertEqual(voiced["from"], silent["from"] + silent["durationInFrames"])
            self.assertEqual(voiced["audio"], "audio/S1-L2.mp3")
            self.assertEqual((episode / "raws/audio/S1-L2.mp3").read_bytes(), b"reused audio")
            self.assertFalse((episode / "raws/audio/000.mp3").exists())

    def test_reactions_keep_duration_at_start_middle_and_end(self):
        board = [
            {"id": "R0", "lines": [], "durationInFrames": 60},
            {"id": "R1", "lines": [], "durationInFrames": 30},
            {"id": "S1", "lines": ["L1"]},
            {"id": "R2", "lines": [], "durationInFrames": 45},
            {"id": "S2", "lines": ["L2"]},
            {"id": "R3", "lines": [], "durationInFrames": 60},
        ]
        character = {"default_outfit": "default", "voice": {}}
        script = lib.normalize_script(
            [{"id": lid, "speaker": "c", "text": lid, "silent": True} for lid in ("L1", "L2")]
        )
        for transitions in (None, {"on": "every-cut", "type": "fade", "durationInFrames": 12}):
            with self.subTest(transitions=transitions), tempfile.TemporaryDirectory() as tmp:
                leading, gaps = prepare.reaction_gaps(board)
                timed, _, _ = prepare.build_timing(
                    script, {"c": character}, {}, Path(tmp), 30, lib.DEFAULT_TIMING,
                    False, 30, False, line_gaps=gaps, leading_frames=leading, board=board,
                )
                self.assertEqual(timed[0]["start"], 90 + lib.DEFAULT_TIMING["lead_in_frames"])
                shots, total, _ = prepare.build_shots(
                    board, timed, lib.DEFAULT_TIMING, {}, {"c": "default"}, transitions, gaps,
                )
                by_id = {shot["id"]: shot for shot in shots}
                for raw in board:
                    if raw["lines"]:
                        continue
                    shot = by_id[raw["id"]]
                    incoming = 12 if transitions and raw["id"] != "R0" else 0
                    outgoing = 12 if transitions and raw["id"] != "R3" else 0
                    self.assertEqual(shot["durationInFrames"], raw["durationInFrames"] + incoming + outgoing)
                self.assertEqual(total, shots[-1]["from"] + shots[-1]["durationInFrames"])


class ShotAudioTest(unittest.TestCase):
    def test_same_basenames_do_not_replace_dialogue_or_other_shot_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raws = root / "raws"
            dialogue = raws / "audio" / "000.mp3"
            dialogue.parent.mkdir(parents=True)
            dialogue.write_bytes(b"dialogue")
            sources = []
            for i in range(2):
                source = root / f"source-{i}" / "000.mp3"
                source.parent.mkdir()
                source.write_bytes(f"system-{i}".encode())
                sources.append(source)
            shots = [{"id": f"S{i}", "systemVoice": str(source)} for i, source in enumerate(sources)]
            prepare.snapshot_shot_audio(shots, root, raws)
            self.assertEqual(dialogue.read_bytes(), b"dialogue")
            self.assertNotEqual(shots[0]["systemVoice"], shots[1]["systemVoice"])
            for i, shot in enumerate(shots):
                self.assertEqual((raws / shot["systemVoice"]).read_bytes(), f"system-{i}".encode())

class ThoughtLineTest(unittest.TestCase):
    def test_thought_synthesis_reuse_silent_and_timing(self):
        script = lib.normalize_script([
            {"id": "M1", "speaker": "c", "kind": "thought", "text": "Thinking"},
            {"id": "M2", "speaker": "c", "kind": "thought", "text": "Quiet", "silent": True},
        ])
        board = [{"id": "S1T", "lines": ["M1"]}, {"id": "S2T", "lines": ["M2"]}]
        def synthesize(text, voice, target, timeout, fallback):
            target.write_bytes(b"tts")
            return {"provider": "test"}
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            with patch.object(prepare.voice, "synthesize_line", side_effect=synthesize) as synth, patch.object(
                lib, "probe_duration", return_value=2.0
            ):
                for reuse in (False, True):
                    timed, _, providers = prepare.build_timing(
                        script, {"c": {"default_outfit": "default", "voice": {}}}, {},
                        episode, 30, lib.DEFAULT_TIMING, reuse, 30, False, board=board,
                    )
                    self.assertEqual(providers["silent"], 1)
                synth.assert_called_once()
                self.assertEqual(synth.call_args.args[0], "Thinking")
                self.assertEqual(synth.call_args.args[2].name, "S1T-M1.mp3")
            shots, _, _ = prepare.build_shots(board, timed, lib.DEFAULT_TIMING, {}, {"c": "default"})
            self.assertEqual(shots[0]["lines"][0]["kind"], "thought")
            self.assertEqual(shots[0]["lines"][0]["audio"], "audio/S1T-M1.mp3")
            self.assertEqual(shots[0]["lines"][0]["durationInFrames"], 60 + lib.DEFAULT_TIMING["tail_frames"])
            self.assertEqual(shots[1]["lines"][0]["audio"], "")
            self.assertFalse((episode / "audio/S2T-M2.mp3").exists())

    def test_thought_coverage_and_legacy_rejection(self):
        script = lib.normalize_script([{"id": "M1", "speaker": "c", "kind": "thought", "text": "Thought"}])
        self.assertEqual(lib.dialogue_audio_names(script, [{"id": "S1T", "lines": ["M1"]}]),
                         {"M1": "S1T-M1.mp3"})
        for board, error in [([], "missing"),
                             ([{"id": "S1T", "lines": ["M1", "M1"]}], "multiply"),
                             ([{"id": "S1T", "lines": ["M1"], "monologue": None}], "script.json")]:
            with self.subTest(board=board), self.assertRaisesRegex(ValueError, error):
                lib.dialogue_audio_names(script, board)
        report = validate.Report(Path("."))
        validate.check_script_and_board(report, {}, script,
                                        {"shots": [{"id": "S1T", "lines": ["M1"], "monologue": {}}]}, {})
        self.assertTrue(any("monologue" in error for error in report.errors))

    def test_kind_validation_and_default(self):
        self.assertEqual(lib.normalize_script([{"text": "Speech"}])[0]["kind"], "speech")
        for kind in ("invalid", None, 1):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "kind"):
                lib.normalize_script([{"text": "Thought", "kind": kind}])

    def test_missing_voiced_thought_audio_is_error_but_silent_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            (episode / "audio").mkdir()
            lib.write_json(episode / "audio/timing.json", {
                "lines": [{"id": "M1", "start": 0, "frames": 60, "audio": ""}],
            })
            for silent in (False, True):
                report = validate.Report(episode)
                validate.check_timing(report, episode, {}, [{"id": "M1", "kind": "thought", "silent": silent}], None)
                self.assertEqual(bool(report.errors), not silent)


if __name__ == "__main__":
    unittest.main()
