import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from moss_transcribe_diarize.app.vllm_runner import VllmRunner, _consume_sse_transcription


class VllmRunnerTest(unittest.TestCase):
    def test_transcribe_posts_openai_compatible_audio_transcription_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "sample.wav"
            sf.write(audio_path, np.zeros(1600, dtype=np.float32), 16000)
            runner = VllmRunner(base_url="http://vllm.test:8000", model="moss-vllm", api_key="secret")
            calls = []

            def fake_post_multipart(url, **kwargs):
                calls.append((url, kwargs))
                return {
                    "text": "[0][S01]hello[1.5]",
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                }

            runner._post_multipart = fake_post_multipart
            status = []
            result = runner.transcribe(
                audio_path,
                prompt="transcribe",
                max_new_tokens=128,
                decoding="sample",
                temperature=0.8,
                status_callback=lambda state, progress, tokens=None: status.append((state, progress, tokens)),
            )

            self.assertEqual(result.text, "[0][S01]hello[1.5]")
            self.assertEqual(result.prompt_len, 11)
            self.assertEqual(result.generated_tokens, 7)
            self.assertEqual(calls[0][0], "http://vllm.test:8000/v1/audio/transcriptions")
            payload = calls[0][1]
            self.assertEqual(payload["fields"]["model"], "moss-vllm")
            self.assertEqual(payload["fields"]["prompt"], "transcribe")
            self.assertEqual(payload["fields"]["response_format"], "json")
            self.assertEqual(payload["fields"]["stream"], "true")
            self.assertEqual(payload["fields"]["stream_include_usage"], "true")
            self.assertEqual(payload["fields"]["stream_continuous_usage_stats"], "true")
            self.assertEqual(payload["fields"]["max_completion_tokens"], "128")
            self.assertEqual(payload["fields"]["temperature"], "0.8")
            self.assertEqual(payload["file_field"], "file")
            self.assertEqual(payload["filename"], "audio.wav")
            self.assertEqual(payload["content_type"], "audio/wav")
            self.assertTrue(payload["file_bytes"])
            self.assertEqual(status[-1], ("transcribing", 0.85, 7))

    def test_transcription_url_accepts_v1_or_full_endpoint(self):
        self.assertEqual(
            VllmRunner(base_url="http://host:8000/v1", model="m")._transcriptions_url(),
            "http://host:8000/v1/audio/transcriptions",
        )
        self.assertEqual(
            VllmRunner(base_url="http://host:8000/v1/audio/transcriptions", model="m")._transcriptions_url(),
            "http://host:8000/v1/audio/transcriptions",
        )

    def test_transcribe_fails_closed_on_empty_zero_token_or_unparseable_output(self):
        cases = [
            ({"text": "[0][S01]hello[1]", "usage": {"prompt_tokens": 1, "completion_tokens": 0}}, "zero generated tokens"),
            ({"text": "", "usage": {"prompt_tokens": 1, "completion_tokens": 2}}, "empty transcript"),
            ({"text": "plain text", "usage": {"prompt_tokens": 1, "completion_tokens": 2}}, "zero parsed segments"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "sample.wav"
            sf.write(audio_path, np.zeros(1600, dtype=np.float32), 16000)

            for response, expected in cases:
                runner = VllmRunner(base_url="http://vllm.test:8000", model="moss-vllm")
                runner._post_multipart = lambda *args, response=response, **kwargs: response

                with self.subTest(expected=expected):
                    with self.assertRaisesRegex(RuntimeError, expected):
                        runner.transcribe(audio_path)

    def test_sse_error_payload_fails_with_context(self):
        response = [
            b'data: {"usage": {"prompt_tokens": 11, "completion_tokens": 0}}\n\n',
            b'data: {"error": {"message": "encoder cache overflow", "type": "BadRequestError"}}\n\n',
            b"data: [DONE]\n\n",
        ]

        with self.assertRaisesRegex(RuntimeError, "encoder cache overflow"):
            _consume_sse_transcription(response, status_callback=None, max_new_tokens=128)


if __name__ == "__main__":
    unittest.main()
