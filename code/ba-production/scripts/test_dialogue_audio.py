"""Offline dialogue naming, reuse and migration contracts."""
import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lib
import prepare
import voice


class DialogueAudioTest(unittest.TestCase):
    def setUp(self):
        self.script = lib.normalize_script([
            {"id": "L1", "speaker": "c", "text": "one"},
            {"id": "L4", "speaker": "c", "text": "four"},
            {"id": "L9", "speaker": "c", "text": "quiet", "silent": True},
        ])
        self.board = [{"id": "S1", "lines": ["L1"]}, {"id": "S2", "lines": ["L4", "L9"]}]
        self.characters = {"c": {"default_outfit": "default", "voice": {"provider": "edge-tts"}}}

    def episode(self, root):
        lib.write_json(root / "storyboard.json", {"shots": self.board})
        (root / "audio").mkdir(exist_ok=True)

    @staticmethod
    def synth(text, cfg, target, *args):
        target.write_bytes(text.encode())
        return {"provider": "edge-tts", "fallback": False}

    def timing(self, root, reuse=True, script=None):
        return prepare.build_timing(
            self.script if script is None else script, self.characters, {}, root,
            30, lib.DEFAULT_TIMING, reuse, 30, False, board=self.board,
        )[0]

    def run_voice(self, root, only="", reuse=False, dry_run=False, sync=True):
        args = argparse.Namespace(episode=str(root), only=only, reuse=reuse, dry_run=dry_run,
                                  fallback=False, sync=sync, timeout=30, keep_going=False, task_timeout=30)
        with patch.object(lib, "resolve_episode", return_value=root), patch.object(
            voice, "load_episode_plan", return_value=({}, self.script, self.characters, {})
        ):
            return voice.cmd_episode(args)

    def test_generation_reorder_snapshots_and_scene_references(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            voice, "synthesize_line", side_effect=self.synth
        ) as synth, patch.object(lib, "probe_duration", return_value=1):
            root = Path(tmp)
            self.episode(root)
            self.assertEqual(self.run_voice(root), 0)
            self.assertEqual(synth.call_count, 2)
            timed = self.timing(root, script=list(reversed(self.script)))
            synth.assert_called()
            self.assertEqual(synth.call_count, 2)
            self.assertEqual({line["id"]: line["audio"] for line in timed},
                             {"L1": "audio/S1-L1.mp3", "L4": "audio/S2-L4.mp3", "L9": ""})
            for name, data in [("S1-L1.mp3", b"one"), ("S2-L4.mp3", b"four")]:
                self.assertEqual((root / "audio" / name).read_bytes(), data)
                self.assertEqual((root / "raws/audio" / name).read_bytes(), data)
            self.assertFalse((root / "audio/S2-L9.mp3").exists())
            self.assertFalse(list((root / "audio").glob("[0-9]*.mp3")))
            timed = self.timing(root)
            shots, _, _ = prepare.build_shots(self.board, timed, lib.DEFAULT_TIMING, {}, {"c": "default"})
            self.assertEqual(shots[1]["lines"][0]["audio"], "audio/S2-L4.mp3")

    def test_prepare_generates_same_names_without_voice_command(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            voice, "synthesize_line", side_effect=self.synth
        ) as synth, patch.object(lib, "probe_duration", return_value=1):
            root = Path(tmp)
            self.timing(root, reuse=False)
            self.assertEqual([call.args[2].name for call in synth.call_args_list],
                             ["S1-L1.mp3", "S2-L4.mp3"])
            self.assertEqual((root / "raws/audio/S2-L4.mp3").read_bytes(), b"four")

    def test_async_generation_and_retrim_use_only_dialogue_names(self):
        self.characters["c"]["voice"] = {"provider": "vocu", "voice_id": "test"}
        def download(url, target, timeout):
            target.write_bytes(url.encode())
            return 1
        with tempfile.TemporaryDirectory() as tmp, patch.object(voice, "_vocu_key", return_value="test"), patch.object(
            voice, "vocu_voice_info", return_value={}
        ), patch.object(voice, "vocu_async_synthesize", return_value=[{"audio": "one"}, {"audio": "four"}]), patch.object(
            voice, "download_audio", side_effect=download
        ), patch.object(voice, "trim_silence") as trim, patch.object(lib, "probe_duration", return_value=1):
            root = Path(tmp)
            self.episode(root)
            self.run_voice(root, sync=False)
            self.assertEqual([call.args[0].name for call in trim.call_args_list], ["S1-L1.mp3", "S2-L4.mp3"])
            trim.reset_mock()
            (root / "audio/mono-S1.mp3").write_bytes(b"thought")
            lib.write_json(root / "script.json", self.script)
            with patch.object(lib, "resolve_episode", return_value=root):
                voice.cmd_retrim(argparse.Namespace(episode=str(root)))
            self.assertEqual([call.args[0].name for call in trim.call_args_list], ["S1-L1.mp3", "S2-L4.mp3"])

    def test_legacy_dry_run_does_not_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.episode(root)
            (root / "audio/000.mp3").write_bytes(b"one")
            lib.write_json(root / "audio/timing.json", {"lines": [{**self.script[0], "audio": "audio/000.mp3"}]})
            self.run_voice(root, only="L1", reuse=True, dry_run=True)
            self.assertFalse((root / "audio/S1-L1.mp3").exists())

    def test_only_regenerates_requested_line_and_silent_never_synthesizes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            voice, "synthesize_line", side_effect=self.synth
        ) as synth, patch.object(lib, "probe_duration", return_value=1):
            root = Path(tmp)
            self.episode(root)
            (root / "audio/S1-L1.mp3").write_bytes(b"recording")
            self.run_voice(root, only="L4,L9")
            self.assertEqual(synth.call_count, 1)
            self.assertEqual((root / "audio/S1-L1.mp3").read_bytes(), b"recording")
            self.run_voice(root, only="L1,L4", reuse=True)
            self.assertEqual(synth.call_count, 1)
            self.run_voice(root, only="L4", dry_run=True)
            self.assertEqual(synth.call_count, 1)

    def test_legacy_migrates_by_saved_id_not_current_position(self):
        for command in ("prepare", "voice"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp, patch.object(
                voice, "synthesize_line", side_effect=AssertionError("must reuse")
            ), patch.object(lib, "probe_duration", return_value=1):
                root = Path(tmp)
                self.episode(root)
                for name, data in [("000.mp3", b"one"), ("001.mp3", b"four")]:
                    (root / "audio" / name).write_bytes(data)
                lib.write_json(root / "audio/timing.json", {"lines": [
                    {**line, "audio": f"audio/{i:03}.mp3"} for i, line in enumerate(self.script[:2])
                ]})
                self.script.reverse()
                if command == "prepare":
                    self.timing(root)
                else:
                    self.run_voice(root, reuse=True)
                self.script.reverse()
                self.assertEqual((root / "audio/S1-L1.mp3").read_bytes(), b"one")
                self.assertEqual((root / "audio/S2-L4.mp3").read_bytes(), b"four")
                self.assertEqual((root / "audio/000.mp3").read_bytes(), b"one")

    def test_unsafe_legacy_fails_before_any_copy_or_synthesis(self):
        for change in ("missing", "text", "speaker", "voice_text", "duplicate", "path"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.episode(root)
                (root / "audio/000.mp3").write_bytes(b"recording")
                entry = {**self.script[0], "audio": "audio/000.mp3"}
                if change in ("text", "speaker", "voice_text"):
                    entry[change] = "changed"
                if change == "path":
                    entry["audio"] = "audio/../000.mp3"
                entries = [entry, entry] if change == "duplicate" else [entry]
                if change != "missing":
                    lib.write_json(root / "audio/timing.json", {"lines": entries})
                with patch.object(voice, "synthesize_line") as synth:
                    with self.assertRaisesRegex(ValueError, "Cannot safely reuse"):
                        self.run_voice(root, reuse=True)
                    synth.assert_not_called()
                self.assertFalse((root / "audio/S1-L1.mp3").exists())

    def test_existing_recording_is_not_overwritten_by_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root / "old.mp3", root / "new.mp3"
            source.write_bytes(b"old")
            target.write_bytes(b"new")
            with self.assertRaises(FileExistsError):
                lib.copy_legacy_dialogue(source, target)
            self.assertEqual(target.read_bytes(), b"new")

    def test_invalid_ids_ownership_and_collisions(self):
        for board in (
            [{"id": "../S1", "lines": ["L1", "L4", "L9"]}],
            [{"id": "S1", "lines": ["L1", "L4", "L9", "L1"]}],
            [{"id": "S1", "lines": ["L1", "unknown"]}],
            [{"id": "S1", "lines": ["L1"]}],
            self.board + [{"id": "s1", "lines": []}],
            [{"id": "mono", "lines": ["L1", "L4", "L9"]}],
        ):
            with self.subTest(board=board), self.assertRaises(ValueError):
                lib.dialogue_audio_names(self.script, board)
        with self.assertRaises(ValueError):
            lib.dialogue_audio_names([{**self.script[0], "id": "L/1"}], [{"id": "S1", "lines": ["L/1"]}])
        with self.assertRaisesRegex(ValueError, "collision"):
            lib.dialogue_audio_names(
                [{**self.script[0], "id": "B-C"}, {**self.script[1], "id": "C"}],
                [{"id": "A", "lines": ["B-C"]}, {"id": "A-B", "lines": ["C"]}],
            )


if __name__ == "__main__":
    unittest.main()
