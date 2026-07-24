from __future__ import annotations

import importlib.util
import hashlib
import json
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from moss_transcribe_diarize.app.model_runner import TranscriptionResult


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


class FakeRunner:
    model_path = "fake-model"

    def __init__(self):
        self.calls = []

    def transcribe(self, audio_path, **kwargs):
        self.calls.append(kwargs)
        callback = kwargs.get("status_callback")
        if callback:
            callback("transcribing", 0.5)
        return TranscriptionResult(
            text="[0][S01]hello[1.5]",
            prompt_len=10,
            generated_tokens=5,
            elapsed_sec=0.01,
            model="fake-model",
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
        )


class BlockingRunner:
    model_path = "fake-model"

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def transcribe(self, audio_path, **kwargs):
        callback = kwargs.get("status_callback")
        if callback:
            callback("transcribing", 0.55, 3)
        self.started.set()
        self.release.wait(timeout=2)
        return TranscriptionResult(
            text="[0][S01]hello[1.5]",
            prompt_len=10,
            generated_tokens=5,
            elapsed_sec=0.01,
            model="fake-model",
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
        )


class NoopRunner:
    model_path = "fake-model"
    device_name = "cpu"
    dtype_name = "float32"

    def transcribe(self, audio_path, **kwargs):
        callback = kwargs.get("status_callback")
        if callback:
            callback("transcribing", 0.5, 1)
        return TranscriptionResult(
            text="[0][S01]hello[1]",
            prompt_len=10,
            generated_tokens=5,
            elapsed_sec=0.01,
            model=self.model_path,
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
        )


class WindowMetadataRunner(NoopRunner):
    def transcribe(self, audio_path, **kwargs):
        return TranscriptionResult(
            text="[0][S01]hello[1]",
            prompt_len=30,
            generated_tokens=15,
            elapsed_sec=0.03,
            model=self.model_path,
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
            window_count=3,
            completed_windows=3,
            possibly_truncated=False,
        )


class CheckpointRecordingRunner(NoopRunner):
    window_seconds = 150
    stride_seconds = 120

    def __init__(self):
        self.checkpoint_dirs: list[Path] = []

    def transcribe(self, audio_path, **kwargs):
        self.checkpoint_dirs.append(Path(kwargs["checkpoint_dir"]))
        return super().transcribe(audio_path, **kwargs)


class BlockingCheckpointRunner(BlockingRunner):
    window_seconds = 150
    stride_seconds = 120

    def __init__(self):
        super().__init__()
        self.checkpoint_dirs: list[Path] = []

    def transcribe(self, audio_path, **kwargs):
        self.checkpoint_dirs.append(Path(kwargs["checkpoint_dir"]))
        return super().transcribe(audio_path, **kwargs)


class IdentityRunner(NoopRunner):
    def transcribe(self, audio_path, **kwargs):
        result = super().transcribe(audio_path, **kwargs)
        result.identity_resolution = {"summary": {"S01": {"windows": 1}}}
        result.identity_summary = {"S01": {"windows": 1}}
        return result


def wait_terminal(client, job_id: str) -> dict:
    job = {}
    for _ in range(80):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"waiting_review", "done", "failed", "cancelled"}:
            return job
        time.sleep(0.025)
    raise AssertionError(f"job {job_id} did not finish: {job}")


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed")
class AppApiTest(unittest.TestCase):
    def make_vllm_app(self, tmpdir: str):
        from moss_transcribe_diarize.app.server import create_app

        app = create_app(
            model_path="unused-local-model",
            runs_dir=tmpdir,
            backend="vllm",
            vllm_base_url="http://vllm.test:8000/v1",
            vllm_model="moss-served",
            max_length=16384,
        )
        app.state.manager.model_runner = NoopRunner()
        return app

    def test_runtime_reports_vllm_backend(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app
        from moss_transcribe_diarize.app.vllm_runner import VllmRunner
        from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="unused-local-model",
                runs_dir=tmpdir,
                backend="vllm",
                vllm_base_url="http://vllm.test:8000/v1",
                vllm_model="moss-served",
            )
            self.assertIsInstance(app.state.manager.model_runner, WindowedRunner)
            self.assertIsInstance(app.state.manager.model_runner.delegate, VllmRunner)
            client = TestClient(app)
            runtime = client.get("/api/runtime")
            self.assertEqual(runtime.status_code, 200)
            model = runtime.json()["model"]
            self.assertEqual(model["backend"], "vllm")
            self.assertEqual(model["path"], "moss-served")
            self.assertEqual(model["base_url"], "http://vllm.test:8000/v1")
            self.assertEqual(model["windowing"], {"window_seconds": 150, "stride_seconds": 120})
            self.assertFalse(model["speaker_identity"]["config"]["tier_b"]["enabled"])
            self.assertEqual(model["speaker_identity"]["availability"]["reason"], "disabled")

    def test_vllm_speaker_identity_enablement_requires_state_path(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ValueError, "--speaker-identity-state"):
                create_app(
                    model_path="unused-local-model",
                    runs_dir=tmpdir,
                    backend="vllm",
                    vllm_base_url="http://vllm.test:8000/v1",
                    speaker_identity_tier_b=True,
                )

    def test_vllm_speaker_identity_enablement_requires_smoke_fixture(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            state = Path(tmpdir) / "state.pt"
            state.write_bytes(b"state")
            with self.assertRaisesRegex(ValueError, "--speaker-identity-fixture"):
                create_app(
                    model_path="unused-local-model",
                    runs_dir=tmpdir,
                    backend="vllm",
                    vllm_base_url="http://vllm.test:8000/v1",
                    speaker_identity_tier_b=True,
                    speaker_identity_state=state,
                )

    def test_vllm_speaker_identity_uses_real_green_preflight_resolver(self):
        from moss_transcribe_diarize.app import speaker_identity
        from moss_transcribe_diarize.app.server import create_app

        class PassingLoadedProvider:
            def __init__(self, state_path, *, device):
                self.state_path = Path(state_path)
                self.device = device

            def load(self):
                return speaker_identity.tier_b_provider_manifest(device=self.device)

            def embed(self, wav_path, intervals):
                self.assert_loaded_input(wav_path, intervals)
                return [1.0] + [0.0] * 255

            def assert_loaded_input(self, wav_path, intervals):
                assert self.state_path.exists()
                assert Path(wav_path).exists()
                assert intervals == [(0.0, 2.0)]

        with tempfile.TemporaryDirectory() as tmpdir:
            state = Path(tmpdir) / "state.pt"
            state.write_bytes(b"state")
            fixture = Path(tmpdir) / "fixture.wav"
            fixture.write_bytes(b"fixture")
            spec = speaker_identity.TierBAssetSpec(
                state_sha256=hashlib.sha256(state.read_bytes()).hexdigest(),
            )
            with (
                patch.object(speaker_identity, "PINNED_TIER_B_ASSET_SPEC", spec),
                patch.object(speaker_identity, "_OnnxWeSpeakerEmbedder", PassingLoadedProvider),
            ):
                app = create_app(
                    model_path="unused-local-model",
                    runs_dir=tmpdir,
                    backend="vllm",
                    vllm_base_url="http://vllm.test:8000/v1",
                    speaker_identity_tier_b=True,
                    speaker_identity_state=state,
                    speaker_identity_fixture=fixture,
                )

            contract = app.state.manager.model_runner.runtime_info()["speaker_identity"]
            self.assertTrue(contract["config"]["tier_b"]["enabled"])
            self.assertTrue(contract["availability"]["available"])
            self.assertEqual(contract["provider"]["state_sha256"], spec.state_sha256)
            self.assertEqual(contract["provider"]["embedding_dimension"], 256)
            self.assertEqual(contract["provider"]["device"], "cpu")
            self.assertEqual(contract["provider"]["smoke"]["fixture"], str(fixture))

    def test_vllm_speaker_identity_rejects_lazy_provider_failure_before_app_construction(self):
        from moss_transcribe_diarize.app import speaker_identity
        from moss_transcribe_diarize.app.server import create_app

        class LazyMissingProvider:
            def __init__(self, state_path, *, device):
                del state_path, device

            def load(self):
                raise ImportError("install the speaker-identity optional extra")

            def embed(self, wav_path, intervals):
                raise AssertionError("embed must not run after provider load fails")

        with tempfile.TemporaryDirectory() as tmpdir:
            state = Path(tmpdir) / "state.pt"
            state.write_bytes(b"state")
            fixture = Path(tmpdir) / "fixture.wav"
            fixture.write_bytes(b"fixture")
            spec = speaker_identity.TierBAssetSpec(
                state_sha256=hashlib.sha256(state.read_bytes()).hexdigest(),
            )
            with (
                patch.object(speaker_identity, "PINNED_TIER_B_ASSET_SPEC", spec),
                patch.object(speaker_identity, "_OnnxWeSpeakerEmbedder", LazyMissingProvider),
                self.assertRaisesRegex(ValueError, "provider_missing"),
            ):
                create_app(
                    model_path="unused-local-model",
                    runs_dir=tmpdir,
                    backend="vllm",
                    vllm_base_url="http://vllm.test:8000/v1",
                    speaker_identity_tier_b=True,
                    speaker_identity_state=state,
                    speaker_identity_fixture=fixture,
                )

    def test_job_lifecycle_and_missing_ffmpeg_render_error(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(model_path="fake-model", runs_dir=tmpdir, max_new_tokens=8)
            runner = FakeRunner()
            app.state.manager.model_runner = runner
            client = TestClient(app)

            created = client.post(
                "/api/jobs",
                files={"file": ("sample.wav", b"audio", "audio/wav")},
                data={
                    "prompt": "custom prompt",
                    "max_new_tokens": "5",
                    "max_len": "456",
                    "decoding": "sample",
                    "temperature": "0.7",
                },
            )
            self.assertEqual(created.status_code, 200)
            job_id = created.json()["id"]

            job = {}
            for _ in range(40):
                job = client.get(f"/api/jobs/{job_id}").json()
                if job["status"] == "waiting_review":
                    break
                time.sleep(0.05)
            self.assertEqual(job["status"], "waiting_review")
            self.assertEqual(job["inference"]["prompt"], "custom prompt")
            self.assertEqual(job["inference"]["max_new_tokens"], 5)
            self.assertEqual(job["inference"]["max_length"], 456)
            self.assertEqual(job["inference"]["decoding"], "sample")
            self.assertEqual(job["inference"]["temperature"], 0.7)
            self.assertEqual(job["usage"]["generated_tokens"], 5)
            self.assertEqual(job["usage"]["max_new_tokens"], 5)
            self.assertTrue(job["usage"]["possibly_truncated"])
            self.assertEqual(runner.calls[-1]["prompt"], "custom prompt")
            self.assertEqual(runner.calls[-1]["max_new_tokens"], 5)
            self.assertEqual(runner.calls[-1]["max_length"], 456)
            self.assertEqual(runner.calls[-1]["decoding"], "sample")
            self.assertEqual(runner.calls[-1]["temperature"], 0.7)

            listed = client.get("/api/jobs")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json()["jobs"][0]["id"], job_id)

            media = client.get(f"/api/jobs/{job_id}/media")
            self.assertEqual(media.status_code, 200)

            rerun = client.post(f"/api/jobs/{job_id}/rerun", json={"max_new_tokens": 10})
            self.assertEqual(rerun.status_code, 200)
            rerun_id = rerun.json()["id"]
            self.assertNotEqual(rerun_id, job_id)
            rerun_job = {}
            for _ in range(40):
                rerun_job = client.get(f"/api/jobs/{rerun_id}").json()
                if rerun_job["status"] == "waiting_review":
                    break
                time.sleep(0.05)
            self.assertEqual(rerun_job["status"], "waiting_review")
            self.assertEqual(rerun_job["media_name"], "sample.wav")
            self.assertEqual(rerun_job["inference"]["max_new_tokens"], 10)
            self.assertEqual(runner.calls[-1]["max_new_tokens"], 10)

            segments = client.get(f"/api/jobs/{job_id}/segments").json()["segments"]
            self.assertEqual(segments[0]["speaker"], "S01")
            segments[0]["text"] = "edited"
            updated = client.put(
                f"/api/jobs/{job_id}/segments",
                json={"segments": segments, "style": {"speaker_names": {"S01": "Alice"}}},
            )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["segments"][0]["text"], "edited")
            self.assertEqual(client.get(f"/api/jobs/{job_id}").json()["subtitle_style"]["speaker_names"]["S01"], "Alice")

            download = client.get(f"/api/jobs/{job_id}/download?kind=srt")
            self.assertEqual(download.status_code, 200)
            self.assertIn("edited", download.text)
            self.assertIn("Alice: edited", download.text)

            class Missing:
                available = False

            with patch("moss_transcribe_diarize.app.jobs.detect_ffmpeg", return_value=Missing()):
                render = client.post(f"/api/jobs/{job_id}/render", json={"style": {}})
            self.assertEqual(render.status_code, 503)

            deleted = client.delete(f"/api/jobs/{job_id}")
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(client.get(f"/api/jobs/{job_id}").status_code, 404)

    def test_running_job_exposes_live_token_progress(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(model_path="fake-model", runs_dir=tmpdir, max_new_tokens=8)
            runner = BlockingRunner()
            app.state.manager.model_runner = runner
            client = TestClient(app)

            created = client.post(
                "/api/jobs",
                files={"file": ("sample.wav", b"audio", "audio/wav")},
                data={"max_new_tokens": "5"},
            )
            self.assertEqual(created.status_code, 200)
            job_id = created.json()["id"]
            self.assertTrue(runner.started.wait(timeout=2))

            running = client.get(f"/api/jobs/{job_id}").json()
            self.assertEqual(running["status"], "transcribing")
            self.assertEqual(running["usage"]["generated_tokens"], 3)
            self.assertEqual(running["usage"]["max_new_tokens"], 5)
            self.assertAlmostEqual(running["progress"], 0.55)

            runner.release.set()
            finished = {}
            for _ in range(40):
                finished = client.get(f"/api/jobs/{job_id}").json()
                if finished["status"] == "waiting_review":
                    break
                time.sleep(0.05)
            self.assertEqual(finished["status"], "waiting_review")
            self.assertEqual(finished["usage"]["generated_tokens"], 5)

    def test_nonterminal_artifact_routes_refuse_stale_files(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.jobs import JobRecord
        from moss_transcribe_diarize.app.server import create_app

        payload = b"audio"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            app = create_app(model_path="fake-model", runs_dir=runs_dir, max_new_tokens=5)
            client = TestClient(app)

            job_dir = runs_dir / "active-job"
            job_dir.mkdir()
            input_path = job_dir / "input.wav"
            input_path.write_bytes(payload)
            job = JobRecord(
                id="active-job",
                status="postprocessing",
                progress=0.85,
                media_name="sample.wav",
                input_path=str(input_path),
                job_dir=str(job_dir),
                inference_prompt="resume prompt",
                max_length=456,
                max_new_tokens=5,
                decoding="greedy",
                temperature=None,
                model="fake-model",
            )
            job.segments_path.write_text('[{"start":0,"end":1,"speaker":"OLD","text":"stale"}]', encoding="utf-8")
            job.srt_path.write_text("stale", encoding="utf-8")
            app.state.manager._jobs[job.id] = job

            self.assertEqual(client.get(f"/api/jobs/{job.id}/segments").status_code, 409)
            self.assertEqual(client.get(f"/api/jobs/{job.id}/download?kind=srt").status_code, 409)
            updated = client.put(f"/api/jobs/{job.id}/segments", json={"segments": []})
            self.assertEqual(updated.status_code, 409)

    def test_job_persists_runner_window_metadata_through_reload(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(model_path="fake-model", runs_dir=tmpdir, max_new_tokens=5)
            app.state.manager.model_runner = WindowMetadataRunner()
            client = TestClient(app)

            created = client.post(
                "/api/jobs",
                files={"file": ("sample.wav", b"audio", "audio/wav")},
            )
            self.assertEqual(created.status_code, 200)
            job_id = created.json()["id"]
            finished = wait_terminal(client, job_id)
            self.assertEqual(finished["usage"]["generated_tokens"], 15)
            self.assertEqual(finished["usage"]["window_count"], 3)
            self.assertEqual(finished["usage"]["completed_windows"], 3)
            self.assertFalse(finished["usage"]["possibly_truncated"])

            reloaded = create_app(model_path="fake-model", runs_dir=tmpdir, max_new_tokens=5)
            reloaded.state.manager.model_runner = WindowMetadataRunner()
            reloaded_client = TestClient(reloaded)
            persisted = reloaded_client.get(f"/api/jobs/{job_id}").json()
            self.assertEqual(persisted["usage"]["window_count"], 3)
            self.assertEqual(persisted["usage"]["completed_windows"], 3)
            self.assertFalse(persisted["usage"]["possibly_truncated"])

    def test_postprocessing_recovery_discards_stale_finals_and_staging(self):
        from moss_transcribe_diarize.app.jobs import JobManager, JobRecord

        payload = b"audio"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            job_dir = runs_dir / "postprocessing-job"
            job_dir.mkdir()
            input_path = job_dir / "input.wav"
            input_path.write_bytes(payload)
            job = JobRecord(
                id="postprocessing-job",
                status="postprocessing",
                progress=0.85,
                media_name="sample.wav",
                input_path=str(input_path),
                job_dir=str(job_dir),
                inference_prompt="resume prompt",
                max_length=456,
                max_new_tokens=5,
                decoding="greedy",
                temperature=None,
                model="fake-model",
                source_sha256=hashlib.sha256(payload).hexdigest(),
            )
            job.raw_transcript_path.write_text("stale transcript", encoding="utf-8")
            job.segments_path.write_text('[{"start":0,"end":1,"speaker":"OLD","text":"stale"}]', encoding="utf-8")
            job.srt_path.write_text("stale srt", encoding="utf-8")
            job.ass_path.write_text("stale ass", encoding="utf-8")
            job.identity_resolution_path.write_text('{"stale": true}', encoding="utf-8")
            staging_dir = job_dir / ".postprocessing"
            staging_dir.mkdir()
            (staging_dir / "raw_transcript.txt").write_text("staged stale", encoding="utf-8")
            job.job_path.write_text(json.dumps(job.to_dict(), ensure_ascii=False), encoding="utf-8")

            manager = JobManager(
                runs_dir,
                IdentityRunner(),
                prompt="default prompt",
                max_length=123,
                max_new_tokens=9,
            )
            manager._queue.join()

            recovered = manager.get_job(job.id)
            self.assertEqual(recovered.status, "waiting_review")
            self.assertFalse(staging_dir.exists())
            self.assertEqual(recovered.raw_transcript_path.read_text(encoding="utf-8"), "[0][S01]hello[1]")
            self.assertIn("hello", recovered.segments_path.read_text(encoding="utf-8"))
            self.assertNotIn("stale", recovered.srt_path.read_text(encoding="utf-8"))
            self.assertNotIn("stale", recovered.ass_path.read_text(encoding="utf-8"))
            self.assertEqual(
                json.loads(recovered.identity_resolution_path.read_text(encoding="utf-8")),
                {"summary": {"S01": {"windows": 1}}},
            )

    def test_job_persists_checkpoint_lifecycle_fields_and_passes_checkpoint_dir(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        payload = b"audio"
        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(model_path="fake-model", runs_dir=tmpdir, max_new_tokens=5)
            runner = CheckpointRecordingRunner()
            app.state.manager.model_runner = runner
            client = TestClient(app)

            created = client.post(
                "/api/jobs",
                files={"file": ("sample.wav", payload, "audio/wav")},
            )
            self.assertEqual(created.status_code, 200)
            job_id = created.json()["id"]
            finished = wait_terminal(client, job_id)

            expected_sha = hashlib.sha256(payload).hexdigest()
            expected_checkpoint = Path(tmpdir) / job_id / "checkpoint"
            self.assertEqual(finished["source_sha256"], expected_sha)
            self.assertEqual(finished["checkpoint_dir"], str(expected_checkpoint))
            self.assertEqual(finished["checkpoint_state"], "complete")
            self.assertEqual(finished["resume_attempts"], 0)
            self.assertEqual(runner.checkpoint_dirs, [expected_checkpoint])

            persisted = json.loads((Path(tmpdir) / job_id / "job.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["source_sha256"], expected_sha)
            self.assertEqual(persisted["checkpoint_dir"], str(expected_checkpoint))
            self.assertEqual(persisted["checkpoint_state"], "complete")
            self.assertEqual(persisted["resume_attempts"], 0)

    def test_startup_requeues_interrupted_checkpoint_job_once(self):
        from moss_transcribe_diarize.app.jobs import JobManager, JobRecord

        payload = b"audio"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            job_dir = runs_dir / "interrupted-job"
            job_dir.mkdir()
            input_path = job_dir / "input.wav"
            input_path.write_bytes(payload)
            checkpoint_dir = job_dir / "checkpoint"
            job = JobRecord(
                id="interrupted-job",
                status="transcribing",
                progress=0.55,
                media_name="sample.wav",
                input_path=str(input_path),
                job_dir=str(job_dir),
                inference_prompt="resume prompt",
                max_length=456,
                max_new_tokens=5,
                decoding="greedy",
                temperature=None,
                model="fake-model",
                source_sha256=hashlib.sha256(payload).hexdigest(),
                checkpoint_dir=str(checkpoint_dir),
                checkpoint_state="running",
            )
            job.job_path.write_text(json.dumps(job.to_dict(), ensure_ascii=False), encoding="utf-8")

            runner = CheckpointRecordingRunner()
            manager = JobManager(
                runs_dir,
                runner,
                prompt="default prompt",
                max_length=123,
                max_new_tokens=9,
            )
            manager._queue.join()

            recovered = manager.get_job(job.id)
            self.assertEqual(recovered.status, "waiting_review")
            self.assertEqual(recovered.progress, 0.95)
            self.assertEqual(recovered.error, None)
            self.assertEqual(recovered.resume_attempts, 0)
            self.assertEqual(recovered.checkpoint_state, "complete")
            self.assertEqual(runner.checkpoint_dirs, [checkpoint_dir])
            persisted = json.loads(job.job_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "waiting_review")
            self.assertEqual(persisted["checkpoint_state"], "complete")
            self.assertEqual(persisted["resume_attempts"], 0)

    def test_resume_failed_checkpoint_job_is_idempotent_while_active(self):
        from moss_transcribe_diarize.app.jobs import JobManager, JobRecord

        payload = b"audio"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            job_dir = runs_dir / "failed-job"
            job_dir.mkdir()
            input_path = job_dir / "input.wav"
            input_path.write_bytes(payload)
            checkpoint_dir = job_dir / "checkpoint"
            job = JobRecord(
                id="failed-job",
                status="failed",
                progress=1.0,
                media_name="sample.wav",
                input_path=str(input_path),
                job_dir=str(job_dir),
                inference_prompt="resume prompt",
                max_length=456,
                max_new_tokens=5,
                decoding="greedy",
                temperature=None,
                model="fake-model",
                source_sha256=hashlib.sha256(payload).hexdigest(),
                checkpoint_dir=str(checkpoint_dir),
                checkpoint_state="failed",
                resume_attempts=2,
                error="window failed",
            )
            job.job_path.write_text(json.dumps(job.to_dict(), ensure_ascii=False), encoding="utf-8")

            runner = BlockingCheckpointRunner()
            manager = JobManager(
                runs_dir,
                runner,
                prompt="default prompt",
                max_length=123,
                max_new_tokens=9,
            )

            resumed = manager.resume_job(job.id)
            self.assertEqual(resumed.id, job.id)
            self.assertEqual(resumed.status, "queued")
            self.assertEqual(resumed.resume_attempts, 3)
            self.assertEqual(resumed.error, None)
            self.assertEqual(resumed.checkpoint_state, "ready")
            self.assertTrue(runner.started.wait(timeout=2))

            active = manager.resume_job(job.id)
            self.assertIn(active.status, {"queued", "loading_model", "transcribing", "postprocessing", "rendering"})
            self.assertEqual(active.resume_attempts, 3)

            runner.release.set()
            manager._queue.join()
            finished = manager.get_job(job.id)
            self.assertEqual(finished.status, "waiting_review")
            self.assertEqual(finished.resume_attempts, 3)
            self.assertEqual(runner.checkpoint_dirs, [checkpoint_dir])

    def test_resume_rejects_terminal_and_non_checkpoint_jobs(self):
        from moss_transcribe_diarize.app.jobs import JobManager, JobRecord

        payload = b"audio"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runner = CheckpointRecordingRunner()
            manager = JobManager(
                runs_dir,
                runner,
                prompt="default prompt",
                max_length=123,
                max_new_tokens=9,
            )
            for status in ("waiting_review", "done", "cancelled"):
                with self.subTest(status=status):
                    job_dir = runs_dir / f"{status}-job"
                    job_dir.mkdir()
                    input_path = job_dir / "input.wav"
                    input_path.write_bytes(payload)
                    job = JobRecord(
                        id=f"{status}-job",
                        status=status,
                        progress=1.0,
                        media_name="sample.wav",
                        input_path=str(input_path),
                        job_dir=str(job_dir),
                        inference_prompt="resume prompt",
                        max_length=456,
                        max_new_tokens=5,
                        decoding="greedy",
                        temperature=None,
                        model="fake-model",
                        source_sha256=hashlib.sha256(payload).hexdigest(),
                        checkpoint_dir=str(job_dir / "checkpoint"),
                        checkpoint_state="complete",
                    )
                    manager._jobs[job.id] = job
                    with self.assertRaises(RuntimeError):
                        manager.resume_job(job.id)
                    self.assertEqual(job.resume_attempts, 0)

            legacy_dir = runs_dir / "legacy-failed"
            legacy_dir.mkdir()
            legacy_input = legacy_dir / "input.wav"
            legacy_input.write_bytes(payload)
            legacy = JobRecord(
                id="legacy-failed",
                status="failed",
                progress=1.0,
                media_name="sample.wav",
                input_path=str(legacy_input),
                job_dir=str(legacy_dir),
                inference_prompt="resume prompt",
                max_length=456,
                max_new_tokens=5,
                decoding="greedy",
                temperature=None,
                model="fake-model",
            )
            manager._jobs[legacy.id] = legacy
            with self.assertRaises(RuntimeError):
                manager.resume_job(legacy.id)
            self.assertEqual(runner.checkpoint_dirs, [])

    def test_resume_api_queues_same_job_and_rerun_still_creates_new_job(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.jobs import JobRecord
        from moss_transcribe_diarize.app.server import create_app

        payload = b"audio"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            app = create_app(model_path="fake-model", runs_dir=runs_dir, max_new_tokens=5)
            runner = BlockingCheckpointRunner()
            app.state.manager.model_runner = runner
            client = TestClient(app)

            job_dir = runs_dir / "api-failed"
            job_dir.mkdir()
            input_path = job_dir / "input.wav"
            input_path.write_bytes(payload)
            checkpoint_dir = job_dir / "checkpoint"
            job = JobRecord(
                id="api-failed",
                status="failed",
                progress=1.0,
                media_name="sample.wav",
                input_path=str(input_path),
                job_dir=str(job_dir),
                inference_prompt="resume prompt",
                max_length=456,
                max_new_tokens=5,
                decoding="greedy",
                temperature=None,
                model="fake-model",
                source_sha256=hashlib.sha256(payload).hexdigest(),
                checkpoint_dir=str(checkpoint_dir),
                checkpoint_state="failed",
                error="window failed",
            )
            app.state.manager._jobs[job.id] = job
            app.state.manager._save_job(job)

            response = client.post(f"/api/jobs/{job.id}/resume")
            self.assertEqual(response.status_code, 200)
            resumed = response.json()
            self.assertEqual(resumed["id"], job.id)
            self.assertEqual(resumed["resume_attempts"], 1)
            self.assertTrue(runner.started.wait(timeout=2))

            active = client.post(f"/api/jobs/{job.id}/resume")
            self.assertEqual(active.status_code, 200)
            self.assertEqual(active.json()["id"], job.id)
            self.assertEqual(active.json()["resume_attempts"], 1)

            runner.release.set()
            finished = wait_terminal(client, job.id)
            self.assertEqual(finished["status"], "waiting_review")
            self.assertEqual(finished["resume_attempts"], 1)
            self.assertEqual(runner.checkpoint_dirs, [checkpoint_dir])

            terminal = client.post(f"/api/jobs/{job.id}/resume")
            self.assertEqual(terminal.status_code, 409)

            rerun = client.post(f"/api/jobs/{job.id}/rerun", json={"max_new_tokens": 6})
            self.assertEqual(rerun.status_code, 200)
            self.assertNotEqual(rerun.json()["id"], job.id)
            wait_terminal(client, rerun.json()["id"])

    def test_vllm_runtime_reports_deployed_context_cap(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            client = TestClient(self.make_vllm_app(tmpdir))
            runtime = client.get("/api/runtime")
            self.assertEqual(runtime.status_code, 200)
            self.assertEqual(runtime.json()["inference"]["max_length"], 16384)

    def test_index_omits_static_context_default(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            client = TestClient(self.make_vllm_app(tmpdir))
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('id="maxLen" type="number" min="1" step="1" value=', response.text)

    def test_vllm_upload_accepts_value_equal_to_deployed_cap(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            client = TestClient(self.make_vllm_app(tmpdir))
            response = client.post(
                "/api/jobs",
                files={"file": ("sample.wav", b"audio", "audio/wav")},
                data={"max_len": "16384"},
            )
            self.assertEqual(response.status_code, 200)
            wait_terminal(client, response.json()["id"])

    def test_vllm_upload_rejects_value_above_deployed_cap(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            client = TestClient(self.make_vllm_app(tmpdir))
            response = client.post(
                "/api/jobs",
                files={"file": ("sample.wav", b"audio", "audio/wav")},
                data={"max_len": "131072"},
            )
            if response.status_code == 200:
                wait_terminal(client, response.json()["id"])
            self.assertEqual(response.status_code, 400)
            self.assertIn("max_len", response.json()["detail"])
            self.assertIn("16384", response.json()["detail"])

    def test_vllm_rerun_rejects_value_above_deployed_cap(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            client = TestClient(self.make_vllm_app(tmpdir))
            created = client.post(
                "/api/jobs",
                files={"file": ("sample.wav", b"audio", "audio/wav")},
                data={"max_len": "16384"},
            )
            self.assertEqual(created.status_code, 200)
            source_id = created.json()["id"]
            wait_terminal(client, source_id)

            response = client.post(f"/api/jobs/{source_id}/rerun", json={"max_len": 131072})
            if response.status_code == 200:
                wait_terminal(client, response.json()["id"])
            self.assertEqual(response.status_code, 400)
            self.assertIn("max_len", response.json()["detail"])
            self.assertIn("16384", response.json()["detail"])

    def test_vllm_rerun_rejects_explicit_invalid_max_len_values(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            client = TestClient(self.make_vllm_app(tmpdir))
            created = client.post(
                "/api/jobs",
                files={"file": ("sample.wav", b"audio", "audio/wav")},
                data={"max_len": "16384"},
            )
            self.assertEqual(created.status_code, 200)
            source_id = created.json()["id"]
            wait_terminal(client, source_id)

            for value in (0, -1, "abc"):
                with self.subTest(max_len=value):
                    response = client.post(f"/api/jobs/{source_id}/rerun", json={"max_len": value})
                    if response.status_code == 200:
                        wait_terminal(client, response.json()["id"])
                    self.assertEqual(response.status_code, 400)

    def test_hf_backend_retains_configured_max_len_behavior(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app
        from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(model_path="fake-model", runs_dir=tmpdir, max_length=131072)
            self.assertNotIsInstance(app.state.manager.model_runner, WindowedRunner)
            app.state.manager.model_runner = NoopRunner()
            client = TestClient(app)
            response = client.post(
                "/api/jobs",
                files={"file": ("sample.wav", b"audio", "audio/wav")},
                data={"max_len": "131072"},
            )
            self.assertEqual(response.status_code, 200)
            job = wait_terminal(client, response.json()["id"])
            self.assertEqual(job["inference"]["max_length"], 131072)


if __name__ == "__main__":
    unittest.main()
