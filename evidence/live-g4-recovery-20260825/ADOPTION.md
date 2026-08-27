# G4 recovery adoption record — pre-change

Captured 2026-08-25 EDT before any production edit.

## Repository

- Branch: `ralph/live-convergence-0824`
- HEAD: `7608c91ce36441d9075fbba41e18c5fae8f464ac`
- Tracked production diff: empty
- Empty production-patch SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- User-owned untracked roots were preserved: the live-policy evidence/prototypes, live-surface
  evidence/prototypes, plan, and handoff shown by `git status --short`.

Production-file SHA-256 before the change:

```text
3554ee297d353a16a18802e93bbdbefe6529d550c6eb7320a8f368972688f83e  moss_transcribe_diarize/app/live_transcript_convergence.py
9b780b00b14ab388a8a3075d2b2cadf93cb90ce830a24c38e2b5094a77446aac  moss_transcribe_diarize/app/live_coordinator.py
959063978daf7ae58fce380e49537af61dc0ab1db4184c7566c823fdf6147e5c  moss_transcribe_diarize/app/live_service_runtime.py
443cf6405c39b5fbdf6a11ebf22e71eb996d6e960c4acbbebeb599cb20cd8f3f  moss_transcribe_diarize/app/live_session.py
```

## Existing development service

- PID/start: `37488`, `Tue Aug 25 11:28:31 2026`
- CWD: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize`
- Listener: `*:7861`
- Command SHA-256: `89d144eaa26445ede0683a8d24ee73299d405a6c194a77b8aa52768220bbf652`
- Command: `.venv/bin/python -m moss_transcribe_diarize.app.web_cli --backend vllm --model OpenMOSS-Team/MOSS-Transcribe-Diarize --vllm-base-url http://127.0.0.1:18000/v1 --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize --vllm-timeout 1800 --runs-dir /Users/gao/.local/share/moss-transcribe-diarize/dev-runs --host 0.0.0.0 --port 7861 --max-len 16384 --max-new-tokens 12000 --live --live-provider-manifest /Users/gao/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json --live-auth-state /Users/gao/.local/share/moss-transcribe-diarize/g3/live-auth.json --live-shared-token-file /Users/gao/.local/share/moss-transcribe-diarize/g3/shared-token --live-tls-certfile /Users/gao/.local/share/moss-transcribe-diarize/g3/live-cert.pem --live-tls-keyfile /Users/gao/.local/share/moss-transcribe-diarize/g3/live-key.pem --live-helper-lease-seconds 30 --live-vector-journal-path /Users/gao/.local/share/moss-transcribe-diarize/g3/vector-journal.jsonl`

Runtime descriptor before the change:

```text
source_revision=29681e0479305449bb40caa49154fe4b1ae85eea
provider=moss-rtx-webrtc-wespeaker
provider_revision=webrtcvad-wheels-2.0.14+wespeaker-4adba1525a6c9d5fff74b6df43a6ec97a86c4112
provider_manifest_hash=07e325988de150ca12d18aee5b9c941679d1af57fd9a6da8b2eec6cf68c08313
combined_config_hash=431efb3f5c0c3d0b685a8121b4e72eee08fc8072001f6d9b178e924321d7a265
decoder_config_hash=20d2492f30df9f24bbe1403f4d163cc465428347c6d14dbd1116bd571d4f973c
endpoint_config_hash=9dc3bc6b957431698627b06b56da46029b20d98e8df8a7b64574153adcfcb222
identity_config_hash=4b7c94eddf0d566bd7870ce7fbe6464d3a5f75d80371c0eb4dd36fb64fec9b89
sample_rate=16000 frame_samples=8000 hard_cap_samples=40000 max_queue_depth=16
```

Remote model before the change:

```text
base_url=http://127.0.0.1:18000/v1
model=OpenMOSS-Team/MOSS-Transcribe-Diarize
vllm_num_requests_running=0
vllm_num_requests_waiting=0
```

## Corpus and controlling evidence

- Immutable corpus manifest:
  `evidence/live-policy-sweep-20260825/corpus/corpus-manifest.json`, SHA-256
  `80fc15bd730f7aa44d8a69aa6e7e00aaf43ed54e2af8a03abc2c8934d7438d7c`.
- Six WAV and six reference hashes were recomputed and matched the manifest exactly.
- F1–F4 source:
  `evidence/live-policy-sweep-20260825/G4-root-cause/NOTES.md` (SHA-256
  `a8535120939d93366a87e48252c9e126d1ab809c26b2ef3f754f7d9b8e5de91a`).
- Jamie retained probe:
  `evidence/live-policy-sweep-20260825/G4-root-cause/probe-output.txt` (SHA-256
  `a6861e5d3ba8fd67f5e4492552aa7bd934d30e4c984eefe5c34f9f0f071159bf`).
- Quiet-GPU control:
  `evidence/live-policy-sweep-20260825/G4-root-cause/quiet-gpu-jamie-summary.json`
  (SHA-256 `45054f171fd216920bc01c27ea22321c8f17f63ad18d0404269199f0ceaf9584`).
- F5 and six-case baseline source:
  `evidence/live-policy-sweep-20260825/REPORT.md` (SHA-256
  `123ed78720bf6261bff7cbed5d36049ec895baea9833993fbc36da83962bc6ab`).

