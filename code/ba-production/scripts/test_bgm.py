import tempfile
import unittest
from pathlib import Path

import prepare
import validate


class BgmTest(unittest.TestCase):
    def test_same_named_tracks_are_isolated_and_anchors_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            raws = episode / "raws"
            dialogue = raws / "audio/000.mp3"
            dialogue.parent.mkdir(parents=True)
            dialogue.write_bytes(b"dialogue")
            sources = []
            for index in range(3):
                source = episode / str(index) / "000.mp3"
                source.parent.mkdir()
                source.write_bytes(f"track-{index}".encode())
                sources.append(str(source))
            shots = [{"id": "S1", "from": 0, "durationInFrames": 120,
                      "lines": [{"id": "L1", "from": 30}]},
                     {"id": "S2", "from": 108, "durationInFrames": 132}]
            cfg = {"file": sources[0], "mute": [
                {"from": "S1", "to": "S2", "atLine": "L1", "offsetFrames": 15}],
                "cues": [{"file": source, "from": "S1", "atLine": "L1", "offsetFrames": 15}
                         for source in sources[1:]]}
            bgm = prepare.prepare_bgm(cfg, shots, episode, raws)
            self.assertEqual(dialogue.read_bytes(), b"dialogue")
            tracks = [bgm, *bgm["cues"]]
            self.assertEqual(len({track["src"] for track in tracks}), 3)
            for index, track in enumerate(tracks):
                self.assertEqual((raws / track["src"]).read_bytes(), f"track-{index}".encode())
            self.assertEqual(bgm["muteRanges"], [{"from": 45, "durationInFrames": 195}])
            self.assertEqual(bgm["cues"][0]["from"], 45)
            self.assertEqual(bgm["cues"][0]["durationInFrames"], 75)
            report = validate.Report(episode)
            validate.check_bgm(report, bgm, raws, 240)
            self.assertEqual(report.errors, [])

    def test_offset_past_end_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            source = episode / "track.mp3"
            source.write_bytes(b"track")
            cfg = {"file": str(source), "mute": [
                {"from": "S1", "atLine": "L1", "offsetFrames": 80}]}
            shots = [{"id": "S1", "from": 0, "durationInFrames": 100,
                      "lines": [{"id": "L1", "from": 20}]}]
            with self.assertRaises(SystemExit):
                prepare.prepare_bgm(cfg, shots, episode, episode / "raws")

    def test_validate_reports_missing_cues_and_invalid_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            raws = Path(tmp)
            (raws / "base.mp3").write_bytes(b"base")
            for kind in ("muteRanges", "cues"):
                for start, length in ((-1, 10), (0, 0), (90, 11), ("0", 10)):
                    report = validate.Report(raws)
                    validate.check_bgm(report, {"src": "base.mp3", kind: [
                        {"from": start, "durationInFrames": length, "src": "missing.mp3"}]}, raws, 100)
                    self.assertTrue(any("时间范围" in error for error in report.errors))
                    if kind == "cues":
                        self.assertTrue(any("missing.mp3" in error for error in report.errors))


if __name__ == "__main__":
    unittest.main()
