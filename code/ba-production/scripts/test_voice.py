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
        response.ok = True
        response.content = body
        return response

    def test_vocu_request(self):
        metadata = self._response(
            "application/json",
            json.dumps({"status": 200, "data": {"audio": "https://cdn.example/audio.mp3", "credit_used": 12}}).encode(),
        )
        audio = self._response("audio/mpeg", b"mp3-test")
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            lib, "env_value", return_value="secret"
        ), patch.object(voice.requests, "request") as open_url:
            open_url.side_effect = [metadata, audio]
            out = Path(tmp) / "test.mp3"
            voice.synth_voice("你好 & test?", {"provider": "vocu", "voice_id": "market:abc", "speed": 1.2}, out, 360)
            request = open_url.call_args_list[0]
            self.assertEqual(request.args, ("POST", "https://v1.wusound.cn/api/tts/simple-generate"))
            self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer secret")
            payload = json.loads(request.kwargs["data"])
            self.assertEqual(payload["voiceId"], "market:abc")
            self.assertEqual(payload["text"], "你好 & test?")
            self.assertEqual(payload["speechRate"], 1.2)
            self.assertEqual(open_url.call_args_list[0].kwargs["timeout"], 360)
            download = open_url.call_args_list[1]
            self.assertEqual(download.args, ("GET", "https://cdn.example/audio.mp3"))
            self.assertIsNone(download.kwargs["headers"])
            self.assertEqual(out.read_bytes(), b"mp3-test")

    def test_download_answers_bot_challenge(self):
        challenge = self._response(
            "text/html",
            b'<script>function a(a){function n(){switch(n[e++]){case"0":t+="EO_Bot_Ssid=";continue;'
            b'case"3":t=a[_0x649a("0x7")](t,3697606656);continue}}var e={WTKkN:1022526240,bOYDu:675298258,'
            b'dtzqS:function(a,n){return a+n},wyeCN:99454117,pCQRM:function(a){return a()}},t=0;return t}</script>',
        )
        audio = self._response("audio/mpeg", b"ID3audio")
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            voice.requests, "request", side_effect=[challenge, audio]
        ) as request:
            out = Path(tmp) / "001.mp3"
            out.write_bytes(b"old")
            voice.download_audio("https://cdn.example/a.mp3", out, 30)
            self.assertEqual(
                request.call_args_list[1].kwargs["headers"],
                {"Cookie": "__tst_status=1797278615#; EO_Bot_Ssid=3697606656"},
            )
            self.assertEqual(out.read_bytes(), b"ID3audio")

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            voice.requests, "request", return_value=challenge
        ), patch.object(voice.time, "sleep"):
            out = Path(tmp) / "001.mp3"
            out.write_bytes(b"old")
            with self.assertRaises(RuntimeError):
                voice.download_audio("https://cdn.example/a.mp3", out, 30)
            self.assertEqual(out.read_bytes(), b"old")

    def test_vocu_response_validation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            lib, "env_value", return_value="secret"
        ), patch.object(voice.requests, "request") as open_url:
            out = Path(tmp) / "test.mp3"
            open_url.side_effect = [self._response("application/json", b"{}")]
            with self.assertRaises(RuntimeError):
                voice.synth_vocu("test", {"voice_id": "abc"}, out, 1)
            open_url.side_effect = [
                self._response("application/json", b'{"data":{"audio":"https://cdn.example/a.mp3"}}'),
                self._response("audio/mpeg", b""),
            ]
            with self.assertRaises(RuntimeError):
                voice.synth_vocu("test", {"voice_id": "abc"}, out, 1)

    def test_missing_key(self):
        with patch.object(lib, "env_value", return_value=""), patch.object(voice.requests, "request") as request:
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

    def test_voice_text_keeps_subtitle(self):
        script = lib.normalize_script(
            [
                {"id": "L1", "speaker": "a", "text": "字幕", "voice_text": " よみあげ  "},
                {"id": "L2", "speaker": "a", "text": "字幕だけ"},
            ]
        )
        self.assertEqual(script[0]["text"], "字幕")
        self.assertEqual(lib.spoken_text(script[0]), "よみあげ")
        self.assertNotIn("voice_text", script[1])
        self.assertEqual(lib.spoken_text(script[1]), "字幕だけ")

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
