"""Offline provider contract and fallback tests."""
import io
import json
import math
import struct
import tempfile
import unittest
import wave
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import jsonschema
import lib
import voice


class VoiceTests(unittest.TestCase):
    GPT_VOICE = {
        "provider": "gpt-sovits", "base_url": "http://localhost:9880/",
        "ref_audio_path": "/server/references/momoi.wav",
        "text_lang": "ja", "prompt_lang": "ja", "prompt_text": "参考文本",
        "speed": 1.2,
    }

    def test_gpt_sovits_request_and_mp3_pipeline(self):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setparams((1, 2, 32000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 32000)))
                for i in range(16000)
            ))
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            voice.requests, "request", return_value=self._response("audio/wav", buffer.getvalue())
        ) as request:
            out = Path(tmp) / "sample.mp3"
            used = voice.synthesize_line("こんにちは", self.GPT_VOICE, out, 30, False)
            self.assertEqual(used["provider"], "gpt-sovits")
            self.assertGreater(lib.probe_duration(out), 0)
            with voice.av.open(str(out)) as result:
                self.assertEqual(result.streams.audio[0].codec_context.name, "mp3float")
            self.assertEqual(request.call_args.args, ("POST", "http://localhost:9880/tts"))
            self.assertEqual(request.call_args.kwargs["timeout"], 30)
            payload = json.loads(request.call_args.kwargs["data"])
            self.assertEqual(payload, {
                "text": "こんにちは", "text_lang": "ja",
                "ref_audio_path": self.GPT_VOICE["ref_audio_path"],
                "prompt_lang": "ja", "prompt_text": "参考文本",
                "speed_factor": 1.2, "text_split_method": "cut5",
                "media_type": "wav", "streaming_mode": False,
            })

    def test_gpt_sovits_validation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(voice.requests, "request") as request:
            out = Path(tmp) / "sample.mp3"
            for field in ("ref_audio_path", "text_lang", "prompt_lang"):
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                    voice.synth_gpt_sovits("test", {**self.GPT_VOICE, field: ""}, out, 1)
            with self.assertRaisesRegex(ValueError, "base_url"):
                voice.synth_gpt_sovits("test", {**self.GPT_VOICE, "base_url": "file:///tmp"}, out, 1)
            request.assert_not_called()
            for body in (b"", b'{"error":"invalid reference"}', b"RIFFbad"):
                request.return_value = self._response("application/json", body)
                with self.assertRaisesRegex(RuntimeError, "non-WAV"):
                    voice.synth_gpt_sovits("test", self.GPT_VOICE, out, 1)
                self.assertFalse(out.exists())
            request.return_value.ok = False
            request.return_value.status_code = 400
            with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
                voice.synth_gpt_sovits("test", self.GPT_VOICE, out, 1)

    def test_gpt_sovits_schema(self):
        schema = json.loads((lib.SCHEMAS / "profile.json").read_text())
        validator = jsonschema.Draft202012Validator({
            "$ref": "#/properties/voice", "properties": schema["properties"],
        })
        validator.validate(self.GPT_VOICE)
        validator.validate({"provider": "edge-tts", "voice_id": "a", "fallback": self.GPT_VOICE})
        for cfg in ({"provider": "vocu"}, {"provider": "gpt-sovits", "voice_id": "a"}):
            with self.assertRaises(jsonschema.ValidationError):
                validator.validate(cfg)

    def test_gpt_sovits_check_is_offline(self):
        args = Namespace(character="test", text="test", config_only=True, synthesize=False)
        with patch.object(lib, "read_character", return_value={"voice": self.GPT_VOICE}), patch.object(
            voice.requests, "request"
        ) as request:
            self.assertEqual(voice.cmd_check(args), 0)
            request.assert_not_called()
        with patch.object(lib, "read_character", return_value={"voice": {"provider": "gpt-sovits"}}):
            self.assertEqual(voice.cmd_check(args), 1)
        cfg = {key: value for key, value in self.GPT_VOICE.items() if key != "base_url"}
        self.assertEqual(voice.gpt_sovits_request("test", cfg)[0], "http://127.0.0.1:9880/tts")

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
        for primary, secondary in [("vocu", "fish-audio"), ("fish-audio", "vocu"), ("edge-tts", "vocu"), ("gpt-sovits", "edge-tts"), ("vocu", "gpt-sovits")]:
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
