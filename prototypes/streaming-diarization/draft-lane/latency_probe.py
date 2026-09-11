"""End-to-end live latency probe against a Phase-2 stack (local or host).

Streams a 16 kHz mono WAV in real time through the real Account Live HTTP API (system lane =
audio, microphone lane = silence, exactly like the acceptance replay client), polls the snapshot
every POLL_S, and records for every transcript segment the wall-clock moment its text first
appeared versus the moment its audio was *sent*. Latency = first_seen - (t0 + segment_start).

Usage: python latency_probe.py --base https://127.0.0.1:17861 --wav <path> [--cafile cert.pem]
       [--seconds 50] [--out results.json]
"""
from __future__ import annotations

import argparse, json, os, ssl, sys, threading, time, urllib.request, wave, difflib, re, tempfile, atexit
from pathlib import Path
from statistics import median


def _ctx(cafile: str | None) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
    return ctx


def bootstrap_cookie(base: str, ctx: ssl.SSLContext, cookie_file: Path) -> None:
    req = urllib.request.Request(base + "/api/workspace/bootstrap", data=b"", method="POST",
                                 headers={"Cookie": "", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
        set_cookie = r.headers.get_all("Set-Cookie") or []
    for line in set_cookie:
        if line.startswith("__Host-moss_session="):
            value = line.split(";", 1)[0].split("=", 1)[1]
            cookie_file.write_text(value + "\n", encoding="utf-8")
            os.chmod(cookie_file, 0o600)
            return
    raise SystemExit("bootstrap returned no session cookie")


def load_pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2, "need 16k mono s16"
        return w.readframes(w.getnframes()), w.getframerate()


def segments_of(snapshot: dict) -> list[dict]:
    """Find the transcript segment list in a snapshot dict without assuming its exact key."""
    session = snapshot.get("session", snapshot)
    for key in ("effective_transcript", "transcript", "segments", "committed_transcript"):
        value = session.get(key)
        if isinstance(value, list) and (not value or isinstance(value[0], dict)):
            return value
        if isinstance(value, dict):
            for k2 in ("segments", "items"):
                if isinstance(value.get(k2), list):
                    return value[k2]
    return []


def visible_segments(snapshot: dict) -> list[dict]:
    from moss_transcribe_diarize.app.live_identity import span_segments
    rows = list(segments_of(snapshot))
    session = snapshot.get("session", {})
    preview = session.get("provisional")
    draft = snapshot.get("draft") if not preview else None
    for suffix in (preview, draft):
        if not suffix or session.get("status") != "active":
            continue
        start, end = suffix["start_sample"], suffix["end_sample"]
        if start != session.get("committed_samples") or end <= start:
            continue
        for seg in span_segments(suffix["transcript"], sample_count=end-start):
            rows.append(dict(text=seg.text, start_sample=start+round(seg.start*16000),
                             end_sample=start+round(seg.end*16000), speaker="S00"))
    return rows


def edit_wer(ref, hyp):
    previous = list(range(len(hyp) + 1))
    for i, word in enumerate(ref, 1):
        current = [i]
        for j, other in enumerate(hyp, 1):
            current.append(min(current[-1]+1, previous[j]+1, previous[j-1]+(word != other)))
        previous = current
    return previous[-1] / len(ref) if ref else None


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def legacy_error(ref: list[str], hyp: list[str]) -> float:
    if not ref:
        return 0.0
    sm = difflib.SequenceMatcher(a=ref, b=hyp, autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks())
    errors = max(len(ref), len(hyp)) - matched
    return errors / len(ref)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--wav", required=True)
    ap.add_argument("--cafile")
    ap.add_argument("--seconds", type=float, default=50.0)
    ap.add_argument("--poll", type=float, default=0.1)
    ap.add_argument("--reference")  # jsonl with {"text": ...}
    ap.add_argument("--out", default="latency-results.json")
    ap.add_argument("--stop-deadline", type=float, default=30.0)
    args = ap.parse_args()

    ctx = _ctx(args.cafile)
    # The replay client uses urllib without a context; make its default trust our local CA.
    ssl._create_default_https_context = lambda *a, **k: ctx  # harness only

    cookie_dir = tempfile.TemporaryDirectory(prefix="moss-draft-probe-")
    atexit.register(cookie_dir.cleanup)
    cookie_file = Path(cookie_dir.name) / "cookie"
    bootstrap_cookie(args.base, ctx, cookie_file)

    from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService
    from moss_transcribe_diarize.app.live_transport import AudioFrame  # noqa: F401
    try:
        from moss_transcribe_diarize.app.live_service_runtime import AudioFrame  # type: ignore
    except Exception:
        pass

    svc = AccountCookieLiveReplayService(base_url=args.base, cookie_file=cookie_file, timeout_seconds=30)
    pcm, rate = load_pcm(Path(args.wav))
    created = svc.create()
    sid = created.session_id
    frame_samples = created.descriptor.frame_samples
    cadence = frame_samples / rate
    total_frames = int(min(args.seconds, len(pcm) / 2 / rate) / cadence)
    print(f"session {sid} frame_samples={frame_samples} cadence={cadence}s frames={total_frames}", flush=True)

    first_seen: dict[str, float] = {}       # segment key -> wall time first seen
    seg_meta: dict[str, dict] = {}
    label_seen: dict[str, float] = {}       # segment key -> wall time a real speaker label appeared
    snapshots = 0
    stop_polling = threading.Event()
    t0_holder: dict[str, float] = {}
    raw_first: dict[str, object] = {}
    covered: dict[int, float] = {}
    covered_label: dict[int, float] = {}

    def poll():
        nonlocal snapshots
        while not stop_polling.is_set():
            try:
                snap = svc._json("GET", f"/api/live/sessions/{svc._quoted(sid)}/snapshot")["snapshot"]
            except Exception as exc:  # noqa: BLE001
                time.sleep(args.poll); continue
            now = time.monotonic()
            snapshots += 1
            if snap and "keys" not in raw_first:
                raw_first["keys"] = list(snap.get("session", snap).keys())
            for seg in visible_segments(snap or {}):
                text = str(seg.get("text", "")).strip()
                if not text:
                    continue
                if isinstance(seg.get("start_sample"), int) and isinstance(seg.get("end_sample"), int):
                    b0 = int(seg["start_sample"] / 8000); b1 = max(b0 + 1, int(seg["end_sample"] / 8000))
                    for b in range(b0, b1):
                        if b not in covered:
                            covered[b] = now
                        spk_ = seg.get("speaker") or seg.get("canonical_speaker") or ""
                        if spk_ and spk_ not in ("S00", "speaker-0000") and b not in covered_label:
                            covered_label[b] = now
                start = seg.get("start", seg.get("start_seconds"))
                if start is None and isinstance(seg.get("start_sample"), int):
                    start = seg["start_sample"] / 16000.0
                key = f"{round(float(start) * 2) / 2 if isinstance(start, (int, float)) else start}"  # audio position bucket; revisions do not count as new
                if key not in first_seen:
                    first_seen[key] = now
                    seg_meta[key] = {"start": start, "end": seg.get("end"), "text": text,
                                     "speaker": seg.get("speaker") or seg.get("canonical_speaker"), "state": seg.get("state") or seg.get("authority")}
                spk = seg.get("speaker") or seg.get("canonical_speaker") or ""
                if spk and spk not in ("S00", "speaker-0000") and key not in label_seen:
                    label_seen[key] = now
            time.sleep(args.poll)

    th = threading.Thread(target=poll, daemon=True); th.start()
    t0 = time.monotonic(); t0_holder["t0"] = t0
    from moss_transcribe_diarize.app.live_service_runtime import AudioFrame as AF
    for seq in range(total_frames):
        target = t0 + seq * cadence
        delay = target - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        off = seq * frame_samples * 2
        chunk = pcm[off: off + frame_samples * 2]
        if len(chunk) < frame_samples * 2:
            chunk = chunk + b"\0" * (frame_samples * 2 - len(chunk))
        svc.accept_frame(sid, AF(sequence=seq, pcm=chunk, sample_count=frame_samples, sample_rate=rate))
    t_sent_end = time.monotonic()
    # Stop and let the terminal pass run; keep polling for label/quality convergence.
    try:
        stop_resp = svc._json("POST", f"/api/live/sessions/{svc._quoted(sid)}/stop", {"deadline": args.stop_deadline}); print("stop pending:", stop_resp.get("code") == "stop_in_progress")
    except Exception as exc:  # noqa: BLE001
        print("stop error class:", type(exc).__name__)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        state = svc._json("GET", f"/api/live/sessions/{svc._quoted(sid)}/snapshot")["snapshot"]
        session = (state or {}).get("session", {})
        if session.get("status") in ("failed", "aborted") or (
            session.get("status") == "closed" and session.get("finalization_status") != "running"
        ):
            break
        time.sleep(.2)
    stop_polling.set(); th.join(timeout=2)
    final = svc._json("GET", f"/api/live/sessions/{svc._quoted(sid)}/snapshot")["snapshot"]

    # Latencies
    lat = []
    lab = []
    for key, seen in first_seen.items():
        start = seg_meta[key]["start"]
        if isinstance(start, (int, float)):
            lat.append((seen - (t0 + float(start)), key))
            if key in label_seen:
                lab.append(label_seen[key] - (t0 + float(start)))
    lat_sorted = sorted(v for v, _ in lat)
    def pct(xs, p):
        return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None
    first_text = min(((seen - t0), seg_meta[k]["start"], seg_meta[k]["text"]) for k, seen in first_seen.items()) if first_seen else None
    result = {
        "base": args.base, "session": sid, "frames": total_frames, "cadence_s": cadence, "snapshots": snapshots,
        "snapshot_keys": raw_first.get("keys"),
        "terminal_failure": {k: v for k, v in ((final or {}).get("terminal_failure") or {}).items()
                             if k in ("kind", "code", "retryable")},
        "first_text": None if not first_text else {"wall_after_start_s": round(first_text[0], 3),
                                                     "audio_start_s": first_text[1], "text": first_text[2][:80]},
        "first_text_latency_s": None if not first_text or not isinstance(first_text[1], (int, float)) else round(first_text[0] - float(first_text[1]), 3),
        "segment_latency_p50_s": None if not lat_sorted else round(pct(lat_sorted, 0.5), 3),
        "segment_latency_p95_s": None if not lat_sorted else round(pct(lat_sorted, 0.95), 3),
        "segment_count": len(lat_sorted),
        "label_delay_p50_s": None if not lab else round(median(lab), 3),
        "labelled_segments": len(lab),
        "final_status": (final or {}).get("session", {}).get("status"),
        "final_finalization": (final or {}).get("session", {}).get("finalization_status"),
        "final_text": " ".join(str(s.get("text", "")) for s in segments_of(final or {})),
        "speakers_final": sorted({str(s.get("speaker") or s.get("canonical_speaker")) for s in segments_of(final or {})}),
        "failure_reason": (final or {}).get("session", {}).get("failure_reason"),
    }
    series = sorted((float(seg_meta[k]["start"]), round(seen - (t0 + float(seg_meta[k]["start"])), 2)) for k, seen in first_seen.items() if isinstance(seg_meta[k]["start"], (int, float)))
    result["latency_by_audio_position"] = series
    result["started_monotonic"] = t0
    result["ended_monotonic"] = time.monotonic()
    result["audio_seconds"] = total_frames * cadence
    result["draft_stats"] = (final or {}).get("draft_stats")
    cov = sorted((b * 0.5, round(t - (t0 + (b + 1) * 0.5), 2)) for b, t in covered.items())
    result["coverage_latency_by_bucket"] = cov
    cov_steady = sorted(l for pos, l in cov if 5.0 <= pos <= (args.seconds - 10.0))
    result["coverage_observed_steady_buckets"] = len(cov_steady)
    result["coverage_p50_s"] = None if not cov_steady else round(pct(cov_steady, 0.5), 3)
    result["coverage_p95_s"] = None if not cov_steady else round(pct(cov_steady, 0.95), 3)
    result["coverage_max_s"] = None if not cov_steady else round(cov_steady[-1], 3)
    lab_cov = sorted(t - (t0 + (b + 1) * 0.5) for b, t in covered_label.items() if 5.0 <= b * 0.5 <= (args.seconds - 10.0))
    result["label_coverage_p50_s"] = None if not lab_cov else round(pct(lab_cov, 0.5), 3)
    result["label_coverage_p95_s"] = None if not lab_cov else round(pct(lab_cov, 0.95), 3)
    steady = [l for pos, l in series if 5.0 <= pos <= (args.seconds - 10.0)]
    steady.sort()
    result["steady_state_p50_s"] = None if not steady else round(pct(steady, 0.5), 3)
    result["steady_state_p95_s"] = None if not steady else round(pct(steady, 0.95), 3)
    result["tail_buckets_after_stop"] = [(pos, l) for pos, l in series if l > 10.0]
    if args.reference:
        ref = " ".join(json.loads(l)["text"] for l in Path(args.reference).read_text().splitlines() if l.strip())
        if result["final_finalization"] == "final":
            result["legacy_sequence_match_error"] = round(legacy_error(words(ref), words(result["final_text"])), 4)
            result["wer_vs_reference"] = round(edit_wer(words(ref), words(result["final_text"])), 4)
        else:
            result["wer_vs_reference"] = None
    result.pop("final_text", None)
    result.pop("failure_reason", None)
    if result["first_text"]: result["first_text"].pop("text", None)
    # Only named content-free telemetry; never retain raw snapshots or exception messages.
    events = svc._json("GET", f"/api/live/sessions/{svc._quoted(sid)}/events")["events"]
    allowed = {"canonical_processed", "canonical_started", "canonical_queued", "draft_published", "rolling_decode_completed"}
    diagnostics = {"terminal_failure": result["terminal_failure"],
                   "events": [e for e in events if e["kind"] in allowed]}
    Path(args.out).with_name(Path(args.out).stem + "-diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    result["stop_deadline_seconds"] = args.stop_deadline
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result.get(k) for k in ("coverage_p50_s", "coverage_p95_s", "first_text_latency_s", "label_coverage_p50_s", "wer_vs_reference", "final_finalization", "draft_stats")}, indent=2))


if __name__ == "__main__":
    main()
