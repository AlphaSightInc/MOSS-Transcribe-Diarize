#!/usr/bin/env python3
"""Disposable visual oracle for LiveTranscribe; synthetic data, no real capture.

Run: python3 tools/uifidelity/reference_oracle.py --port 8765
Uses only the standard library. The reference bundle remains untouched. Only the
served HTML gains localStorage seeds so its normal live-reattach path populates
an otherwise fresh browser. JavaScript, CSS, fonts and images are served verbatim.
REST responses are screenshot fixtures, not a functioning transcription backend.
WebSocket handshakes deliberately fail; HTTP polling keeps the fixture visible.
"""

import argparse
import json
import mimetypes
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

BUNDLE = Path.home() / "Desktop/AI_Projects/LiveTranscribe/ProjectResources/Frontend"
SESSION_ID = "oracle-design-review"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def timestamp(minutes_ago=0):
    return (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


SETTINGS = dict(
    endpointUrl="https://api.example.com/v1", modelName="meeting-assistant",
    temperature=0.2, timeoutSec=60, formatIntervalSec=30, formatInitialDelaySec=30,
    summaryIntervalSec=120, summaryInitialDelaySec=60, targetLanguage="English",
    summaryPrompt="Summarize decisions, open questions, and action items.",
    formatPrompt="Add punctuation and paragraph breaks without changing meaning.",
    customPrompt="", apiKey="",
)
MICROPHONES = [dict(index=0, name="MacBook Pro Microphone", channels=1,
                    sample_rate=48000, is_default=True, eligibility="ok",
                    eligibility_reason=None)]
HISTORY = [dict(session_id=f"oracle-history-{i}", title=title, mode=mode,
                status="completed", audio_path=f"/oracle/{i}.wav",
                started_at=timestamp(i * 1440 + 30), updated_at=timestamp(i * 1440))
           for i, (title, mode) in enumerate([
               ("Product planning · September", "live"),
               ("Customer discovery interview", "file"),
               ("Weekly engineering sync", "live"),
               ("Design critique and next steps", "file"),
           ], 1)]
PROFILES = [dict(profile_id=f"oracle-person-{i}", display_name=name,
                 sample_count=3, last_seen=timestamp(30), created_at=timestamp(1440))
            for i, name in enumerate(["Alex Chen", "Maya Patel", "Jordan Lee"], 1)]
TURNS = [
    ("S01", "Alex Chen", "Thanks for joining. Today we are reviewing the live transcript experience and agreeing on the next steps for the pilot."),
    ("S02", "Maya Patel", "The three-panel layout is working well. I can keep the capture controls open while reading the conversation and checking earlier sessions."),
    ("S03", "Jordan Lee", "During the customer interviews, speaker names made the biggest difference. People could follow the discussion without losing track of who was talking."),
    ("S01", "Alex Chen", "Let’s keep the transcript as the focus. The speaker colors should remain consistent across the legend and each turn in the conversation."),
    ("S02", "Maya Patel", "I will review the controls and the saved-session list at the laptop viewport. We should check spacing, readable timestamps, and the disabled states."),
    ("S03", "Jordan Lee", "I can prepare the sample meeting for tomorrow. It will include three speakers, a few longer responses, and a short summary of our decisions."),
    ("S01", "Alex Chen", "Great. We will compare the screenshots together tomorrow morning, then confirm the remaining work for the pilot."),
]
SEGMENTS = [dict(start=i * 24, end=i * 24 + 21, text=text, speaker=speaker,
                 speaker_entity_id=speaker, display_name=name, confidence=0.96,
                 state="final", segment_id=f"oracle-segment-{i}")
            for i, (speaker, name, text) in enumerate(TURNS)]
SUMMARY = dict(summary="The team reviewed the transcript layout and planned the pilot review.",
               topics=[dict(title="Pilot preparation", description="Validate the three-panel experience.")],
               details=[dict(title="Next review", description="Compare screenshots tomorrow morning.", timestamp="02:24")],
               data_references=[], speaker_background=[])
# All required SessionStatusResponse fields, pinned from authored api/types.ts.
STATUS_DEFAULTS = {'session_id': '', 'status': '', 'mode': '', 'effective_speaker_count': 0, 'live_source': None, 'selected_mic_device_index': None, 'audio_path': '', 'title': '', 'progress_pct': 0, 'output_dir': '', 'started_at': '', 'updated_at': '', 'error': None, 'silence_gate_skips': 0, 'asr_phase': None, 'asr_requests_sent': 0, 'max_inflight_asr_requests': 0, 'capture_phase': None, 'device_name': '', 'negotiated_sample_rate': 0, 'channel_count': 0, 'rms_summary': 0, 'routing_warning': None, 'routing_warning_lane': None, 'routing_warning_detail': None, 'reconnect_guidance': None, 'capture_levels': {}, 'remote_mic_muted': False, 'local_mic_muted': False, 'rms_raw': 0, 'rms_redacted': 0, 'peak_rms_raw': 0, 'peak_capture_mix_rms': 0, 'peak_capture_remote_rms': 0, 'peak_capture_local_rms': 0, 'muted_overlap_seconds': 0, 'muted_segments_dropped_total': 0, 'provisional_requests_sent': 0, 'provisional_empty_asr_result_count': 0, 'provisional_sanitize_empty_count': 0, 'provisional_build_suppressed_count': 0, 'provisional_publish_gated_count': 0, 'provisional_publish_stale_generation_count': 0, 'provisional_last_suppression_reason': None, 'provisional_failure_reason': None, 'provisional_last_visible_lag_sec': 0, 'provisional_max_visible_lag_sec': 0, 'provisional_last_backlog_sec': 0, 'provisional_max_backlog_sec': 0, 'max_transcript_blank_gap_sec': 0, 'provisional_clear_before_canonical_count': 0, 'provisional_schedule_attempt_count': 0, 'provisional_schedule_skip_inflight_count': 0, 'provisional_schedule_skip_empty_count': 0, 'provisional_event_count': 0, 'provisional_heuristic_fallback_count': 0, 'provisional_avg_transcribe_sec': 0, 'provisional_avg_dispatch_delay_sec': 0, 'provisional_avg_end_to_end_sec': 0, 'provisional_steady_avg_end_to_end_sec': 0, 'provisional_first_text_latency_total_sec': 0, 'provisional_first_text_latency_count': 0, 'provisional_first_text_max_latency_sec': 0, 'provisional_first_publish_wall_latency_sec': 0, 'provisional_first_publish_recording_latency_sec': 0, 'provisional_audio_age_at_emit_total_sec': 0, 'provisional_audio_age_at_emit_count': 0, 'canonical_avg_transcribe_sec': 0, 'canonical_avg_diarization_sec': 0, 'canonical_commit_latency_sec': 0, 'canonical_last_commit_latency_sec': 0, 'canonical_last_progress_at_sec': 0, 'canonical_progress_event_count': 0, 'canonical_current_preview_gap_sec': 0, 'canonical_max_preview_gap_sec': 0, 'canonical_progress_stalled': False, 'canonical_progress_stall_count': 0, 'canonical_no_progress_commit_count': 0, 'canonical_recovery_count': 0, 'canonical_progress_stall_threshold_sec': 0, 'canonical_language_hint': None, 'mixed_language_detected': False, 'language_mode_decision': '', 'prompt_mode_decision': '', 'prompt_window_sentences': 0, 'prompt_window_tokens': 0, 'formatted_overlay': {}, 'paragraph_break_after': [], 'summary': None, 'llm_status': '', 'llm_closed': False, 'llm_finalizing': False, 'capture': None}


def session_status(session_id):
    saved = next((item for item in HISTORY if item["session_id"] == session_id), None)
    return dict(STATUS_DEFAULTS, session_id=session_id, status="completed" if saved else "recording",
                mode=saved["mode"] if saved else "live", effective_speaker_count=3,
                live_source="dual", selected_mic_device_index=0,
                audio_path="/oracle/design-review.wav", title=saved["title"] if saved else "Product design review",
                progress_pct=100, output_dir="/oracle", started_at=timestamp(3), updated_at=timestamp(),
                device_name=MICROPHONES[0]["name"], negotiated_sample_rate=48000,
                channel_count=1, capture_phase="recording", capture_levels={},
                formatted_overlay={}, paragraph_break_after=[], llm_status="idle",
                summary=SUMMARY, rms_raw=0.04, rms_summary=0.04)


class OracleHandler(BaseHTTPRequestHandler):
    def reply(self, value, status=200, content_type="application/json; charset=utf-8"):
        payload = json.dumps(value).encode() if content_type.startswith("application/json") else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def handle_request(self):
        path = unquote(urlsplit(self.path).path)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.loads(raw) if raw and "application/json" in self.headers.get("Content-Type", "") else {}
        if path.startswith("/ws/"):
            self.reply(dict(error="WebSocket intentionally unavailable in reference oracle"), 404)
        elif path.startswith("/api/"):
            self.api(path, body)
        else:
            relative = path.removeprefix("/static/").lstrip("/") or "index.html"
            target = (BUNDLE / relative).resolve()
            if not target.is_relative_to(BUNDLE.resolve()) or not target.is_file():
                self.reply(dict(error="Asset not found", path=path), 404)
                return
            payload = target.read_bytes()
            if relative == "index.html":
                seed = ('<script>localStorage.setItem("lt:session:id", "' + SESSION_ID + '");'
                        'localStorage.setItem("lt:ui:controlPanelCollapsed", "false");'
                        'localStorage.setItem("lt:ui:historyPanelCollapsed", "false");</script>')
                payload = payload.replace(b"<head>", b"<head>" + seed.encode(), 1)
            self.reply(payload, content_type=mimetypes.guess_type(target)[0] or "application/octet-stream")

    def api(self, path, body):
        method = self.command
        parts = path.strip("/").split("/")
        result = None
        if path == "/api/settings":
            result = dict(SETTINGS, **body)
        elif path == "/api/devices/input":
            result = dict(devices=MICROPHONES)
        elif path == "/api/devices/live":
            result = dict(microphones=MICROPHONES)
        elif path == "/api/output-volume":
            result = dict(volume_pct=body.get("volume_pct", 65), available=True, message="")
        elif path == "/api/sessions/history":
            result = dict(deleted_count=len(HISTORY)) if method == "DELETE" else dict(sessions=HISTORY)
        elif path.startswith("/api/sessions/history/"):
            result = dict(session_id=parts[-1], deleted=True)
        elif path.startswith("/api/fingerprints"):
            profile_id = parts[2] if len(parts) > 2 else "oracle-person-1"
            if method == "GET":
                result = dict(profiles=PROFILES)
            elif method == "DELETE":
                result = dict(profile_id=profile_id, deleted=True) if len(parts) > 2 else dict(deleted_count=len(PROFILES))
            else:
                result = dict(profile_id=profile_id, display_name=body.get("display_name", "Alex Chen"),
                              saved=True, updated=True)
        elif path.startswith("/api/pick-"):
            result = dict(paths=["/oracle/interview.wav"]) if path == "/api/pick-files" else dict(path="/oracle/interview.wav")
        elif path in ("/api/sessions/start", "/api/sessions/start-file", "/api/sessions/start-url"):
            result = dict(session_id=SESSION_ID, status="recording", mode="live", source_url=body.get("url", ""))
        elif path.startswith("/api/sessions/") and len(parts) >= 3:
            sid = parts[2]
            suffix = "/".join(parts[3:])
            if suffix in ("", "live-reattach", "stop"):
                result = session_status(sid)
                if suffix == "live-reattach":
                    result.update(resumable=True, reattach_reason=None)
                elif suffix == "stop":
                    result.update(status="completed")
            elif suffix == "transcript":
                result = dict(text="\n".join(turn[2] for turn in TURNS), segments=SEGMENTS)
            elif suffix == "llm/settings":
                result = dict(session_id=sid, settings=dict(SETTINGS, **body))
            elif suffix == "llm/state":
                result = dict(session_id=sid, formatted_overlay={}, paragraph_break_after=[],
                              summary=SUMMARY, llm_status="idle", closed=False, finalizing=False)
            elif suffix in ("local-mic", "remote-audio"):
                result = dict(session_id=sid, muted=body.get("muted", False))
            elif suffix == "title":
                result = dict(session_id=sid, title=body.get("title", "Product design review"))
            elif suffix.startswith("speakers/"):
                result = dict(speaker_id=parts[-1], display_name=body.get("display_name", "Alex Chen"), updated=True)
            elif suffix == "summarize":
                result = SUMMARY
            elif suffix.endswith("export-to-folder"):
                result = dict(saved_path="/oracle/" + body.get("file_name", "transcript.txt"))
            elif suffix == "audio/download":
                # Valid silent WAV fixture; no real audio is captured or exported.
                import io
                import wave
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as audio:
                    audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                    audio.writeframes(b"\0" * 32000)
                self.reply(buffer.getvalue(), content_type="audio/wav")
                return
        elif path.startswith("/api/batch/"):
            result = dict(batch_id="oracle-batch", status="completed", total_items=1,
                          started_at=timestamp(10), updated_at=timestamp(), items=[dict(
                              item_index=0, source_type="file", source="/oracle/interview.wav",
                              source_label="interview.wav", display_title="Customer interview",
                              processing_started_at=timestamp(10), status="completed", llm_status="idle",
                              progress_pct=100, output_dir="/oracle", error=None)])
            if path.endswith("/stop"):
                result = dict(cancel_requested=True)
        if result is None:
            self.reply(dict(error="Unknown oracle endpoint", reason="not_stubbed", message=path), 404)
        else:
            self.reply(result)

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request
    do_PATCH = handle_request
    do_DELETE = handle_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not (BUNDLE / "index.html").is_file():
        parser.error(f"Reference bundle not found: {BUNDLE}")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), OracleHandler)
    print(f"Reference oracle: http://127.0.0.1:{server.server_port}/\nBundle: {BUNDLE}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
