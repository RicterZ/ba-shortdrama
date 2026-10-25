import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lib
import prepare


class ReactionTimingTest(unittest.TestCase):
    def test_silent_and_voiced_lines_keep_audio_and_timing_in_shots(self):
        script = lib.normalize_script([
            {"id": "L1", "speaker": "c", "text": "Silent caption", "silent": True},
            {"id": "L2", "speaker": "c", "text": "Voiced caption"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            (episode / "audio").mkdir()
            (episode / "audio/001.mp3").write_bytes(b"reused audio")
            with patch.object(prepare.voice, "synthesize_line") as synth, patch.object(
                lib, "probe_duration", return_value=2.0
            ):
                timed, _, _ = prepare.build_timing(
                    script, {"c": {"default_outfit": "default", "voice": {}}}, {},
                    episode, 30, lib.DEFAULT_TIMING, True, 30, False,
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
            self.assertEqual(voiced["audio"], "audio/001.mp3")
            self.assertEqual((episode / "raws/audio/001.mp3").read_bytes(), b"reused audio")
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
                    False, 30, False, line_gaps=gaps, leading_frames=leading,
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
            prepare.snapshot_shot_audio(shots, {}, root, raws)
            self.assertEqual(dialogue.read_bytes(), b"dialogue")
            self.assertNotEqual(shots[0]["systemVoice"], shots[1]["systemVoice"])
            for i, shot in enumerate(shots):
                self.assertEqual((raws / shot["systemVoice"]).read_bytes(), f"system-{i}".encode())

    def test_custom_monologue_audio_skips_tts_and_extends_reaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            source = episode / "recording.wav"
            source.write_bytes(b"approved voice")
            shot = {"id": "S1", "lines": [], "durationInFrames": 30,
                    "monologue": {"speaker": "c", "text": "thought", "audio": "recording.wav"}}
            with patch.object(prepare.voice, "synthesize_line") as synth, patch.object(
                lib, "probe_duration", return_value=2.0
            ), patch.object(lib, "ROOT", episode / "missing-root"):
                files = prepare.prepare_monologues([shot], {"c": {"voice": {}}}, episode, 30, False, 30, False)
            synth.assert_not_called()
            self.assertEqual(shot["durationInFrames"], 72)
            prepare.snapshot_shot_audio([shot], files, episode, episode / "raws")
            self.assertEqual((episode / "raws" / shot["monologue"]["audio"]).read_bytes(), source.read_bytes())

    def test_missing_custom_audio_does_not_fall_back_to_paid_tts(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(prepare.voice, "synthesize_line") as synth:
            shot = {"id": "S1", "monologue": {"speaker": "c", "text": "thought", "audio": "missing.wav"}}
            with self.assertRaises(SystemExit):
                prepare.prepare_monologues([shot], {"c": {"voice": {}}}, Path(tmp), 30, False, 30, False)
            synth.assert_not_called()

    def test_unprovided_monologue_audio_synthesizes_and_reuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            shot = {"id": "S1", "monologue": {"speaker": "c", "text": "thought"}}
            def synthesize(text, voice, target, timeout, fallback):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"tts")
            with patch.object(prepare.voice, "synthesize_line", side_effect=synthesize) as synth, patch.object(
                lib, "probe_duration", return_value=1.0
            ):
                prepare.prepare_monologues([shot], {"c": {"voice": {}}}, episode, 30, False, 30, False)
                prepare.prepare_monologues([shot], {"c": {"voice": {}}}, episode, 30, True, 30, False)
                self.assertEqual(synth.call_count, 1)


if __name__ == "__main__":
    unittest.main()
