"""Offline media integration tests; no ffmpeg/ffprobe executables needed."""
import math
import os
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import av
import lib
import voice


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "audio.wav"

    def write_audio(self, segments, channels=1):
        rate = 24000
        with wave.open(str(self.path), "wb") as output:
            output.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
            for seconds, tone in segments:
                output.writeframes(b"".join(
                    struct.pack("<h", int(10000 * math.sin(i * 2 * math.pi * 440 / rate)) if tone else 0) * channels
                    for i in range(round(seconds * rate))
                ))

    def test_trim_edges_and_internal_pause_without_path(self):
        for channels in (1, 2):
            with self.subTest(channels=channels):
                self.write_audio([(0.5, False), (1, True), (2, False), (1, True), (0.5, False)], channels)
                with patch.dict(os.environ, {"PATH": ""}):
                    self.assertAlmostEqual(lib.probe_duration(self.path), 5)
                    voice.trim_silence(self.path)
                    # Matches the former CLI filter: detection + retained silence.
                    self.assertAlmostEqual(lib.probe_duration(self.path), 2.9, delta=0.1)
                with av.open(str(self.path)) as audio:
                    self.assertEqual(audio.streams.audio[0].codec_context.channels, channels)
                    self.assertGreater(sum(frame.samples for frame in audio.decode(audio=0)), 0)
                self.assertFalse(self.path.with_suffix(".trim.mp3").exists())

    def test_mp3_input_preserves_short_pause(self):
        self.write_audio([(1, True), (0.2, False), (1, True)])
        voice.trim_silence(self.path)
        mp3 = self.path.with_suffix(".mp3")
        self.path.rename(mp3)
        with patch.dict(os.environ, {"PATH": ""}):
            voice.trim_silence(mp3)
            self.assertAlmostEqual(lib.probe_duration(mp3), 2.2, delta=0.1)

    def test_silent_input_does_not_destroy_source(self):
        self.write_audio([(1, False)])
        original = self.path.read_bytes()
        with self.assertRaises((ValueError, av.error.FFmpegError)):
            voice.trim_silence(self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.path.with_suffix(".trim.mp3").exists())

    def test_invalid_input(self):
        self.path.write_bytes(b"not audio")
        with self.assertRaises(av.error.FFmpegError):
            lib.probe_media(self.path)

    def test_video_stream_and_duration(self):
        path = Path(self.tmp.name) / "video.mp4"
        with av.open(str(path), "w") as container:
            stream = container.add_stream("mpeg4", rate=25)
            stream.width = stream.height = 32
            stream.pix_fmt = "yuv420p"
            for _ in range(25):
                frame = av.VideoFrame(32, 32, "yuv420p")
                for plane in frame.planes:
                    plane.update(bytes(plane.buffer_size))
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode(None):
                container.mux(packet)
        with patch.dict(os.environ, {"PATH": ""}):
            media = lib.probe_media(path)
        self.assertEqual(media["streams"], [{"codec_type": "video"}])
        self.assertAlmostEqual(media["format"]["duration"], 1)


if __name__ == "__main__":
    unittest.main()
