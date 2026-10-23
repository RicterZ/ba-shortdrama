"""Offline provider contract and fallback tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import jsonschema
import lib
import voice


class VoiceTests(unittest.TestCase):
    @staticmethod
    def _response(content_type: str, body: bytes) -> MagicMock:
        response = MagicMock()
        response.headers = {"content-type": content_type}
        response.read.return_value = body
        return response

    def test_vocu_request(self):
        metadata = self._response(
            "application/json",
            json.dumps({"status": 200, "data": {"audio": "https://cdn.example/audio.mp3", "credit_used": 12}}).encode(),
        )
        audio = self._response("audio/mpeg", b"mp3-test")
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            lib, "env_value", return_value="secret"
        ), patch.object(voice.urllib.request, "urlopen") as open_url:
            open_url.return_value.__enter__.side_effect = [metadata, audio]
            out = Path(tmp) / "test.mp3"
            voice.synth_voice("你好 & test?", {"provider": "vocu", "voice_id": "market:abc", "speed": 1.2}, out, 360)
            request = open_url.call_args_list[0].args[0]
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(request.full_url, "https://v1.wusound.cn/api/tts/simple-generate")
            self.assertEqual(request.get_header("Authorization"), "Bearer secret")
            payload = json.loads(request.data)
            self.assertEqual(payload["voiceId"], "market:abc")
            self.assertEqual(payload["text"], "你好 & test?")
            self.assertEqual(payload["speechRate"], 1.2)
            self.assertEqual(open_url.call_args_list[0].kwargs["timeout"], 360)
            download = open_url.call_args_list[1].args[0]
            self.assertEqual(download.full_url, "https://cdn.example/audio.mp3")
            self.assertIsNone(download.get_header("Authorization"))
            self.assertEqual(out.read_bytes(), b"mp3-test")

    def test_vocu_response_validation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            lib, "env_value", return_value="secret"
        ), patch.object(voice.urllib.request, "urlopen") as open_url:
            out = Path(tmp) / "test.mp3"
            open_url.return_value.__enter__.side_effect = [self._response("application/json", b"{}")]
            with self.assertRaises(RuntimeError):
                voice.synth_vocu("test", {"voice_id": "abc"}, out, 1)
            open_url.return_value.__enter__.side_effect = [
                self._response("application/json", b'{"data":{"audio":"https://cdn.example/a.mp3"}}'),
                self._response("audio/mpeg", b""),
            ]
            with self.assertRaises(RuntimeError):
                voice.synth_vocu("test", {"voice_id": "abc"}, out, 1)

    def test_missing_key(self):
        with patch.object(lib, "env_value", return_value=""), patch.object(voice.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(RuntimeError, "VOCU_API_KEY"):
                voice.synth_vocu("test", {"voice_id": "abc"}, Path("unused.mp3"), 1)
            request.assert_not_called()

    def test_fallback_both_directions_and_opt_in(self):
        for primary, secondary in [("vocu", "fish-audio"), ("fish-audio", "vocu"), ("edge-tts", "vocu")]:
            cfg = {"provider": primary, "voice_id": "a", "fallback": {"provider": secondary, "voice_id": "b"}}
            with tempfile.TemporaryDirectory() as tmp, patch.object(voice.time, "sleep"), patch.object(
                voice, "synth_voice", side_effect=[RuntimeError("fail")] * 3 + [None]
            ) as synth:
                used = voice.synth_with_retry("test", cfg, Path(tmp) / "test.mp3", 1, True)
                self.assertEqual(used["provider"], secondary)
                self.assertTrue(used["fallback"])
                self.assertEqual(synth.call_count, 4)
            with patch.object(voice.time, "sleep"), patch.object(voice, "synth_voice", side_effect=RuntimeError("fail")) as synth:
                with self.assertRaises(RuntimeError):
                    voice.synth_with_retry("test", cfg, Path(tmp) / "test.mp3", 1, False)
                self.assertEqual(synth.call_count, 3)

    def test_profiles_and_schema(self):
        schema = json.loads((lib.SCHEMAS / "profile.json").read_text())
        for path in lib.CHARACTERS.glob("*/profile.yaml"):
            profile = json.loads(path.read_text())
            jsonschema.validate(profile, schema)
            invalid = {**profile, "voice": {"provider": "vocu", "voice_id": "a", "fallback": {"provider": "invalid", "voice_id": "b"}}}
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(invalid, schema)


if __name__ == "__main__":
    unittest.main()
