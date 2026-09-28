"""P52 throwaway real-time Gemini words probe. Run from the worktree root.

PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/words/proto_words.py --arm w1 --clip mono_javier_intro_50s
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from google.genai import types

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from corpus import clips  # noqa: E402
from gemini_common import client, diarize_window, ledger, read_wav, spend  # noqa: E402
from score import score  # noqa: E402

RATE = 16000
FRAME = 1600
MODEL = {"w1": "gemini-3.8-live", "w2": "gemini-3.8-live", "w3": "gemini-3.5-transcribe-live"}


def live_config(arm: str, turn_s: int, sensitivity: str, silence_ms: int,
                thinking: int | None, max_output: int | None,
                handle: str | None = None, language_code: str = "en") -> types.LiveConnectConfig:
    manual = arm == "w2" or (arm == "w3" and turn_s > 0)
    vad = types.AutomaticActivityDetection(
        disabled=manual,
        end_of_speech_sensitivity=("END_SENSITIVITY_HIGH" if sensitivity == "high" else "END_SENSITIVITY_LOW") if not manual else None,
        silence_duration_ms=silence_ms if not manual else None,
        prefix_padding_ms=100 if not manual else None,
    )
    d = dict(
        response_modalities=["AUDIO"] if arm in ("w1", "w2") else ["TEXT"],
        input_audio_transcription=types.AudioTranscriptionConfig(
            mode="VERBATIM", language_codes=None if language_code == "auto" else [language_code],
            word_timestamp=True),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=vad,
            activity_handling="NO_INTERRUPTION", turn_coverage="TURN_INCLUDES_ALL_INPUT"),
        session_resumption=types.SessionResumptionConfig(handle=handle),
        system_instruction=("Transcribe the user's audio. Remain silent. Never produce spoken audio." if arm in ("w1", "w2") else "Transcribe the input audio verbatim. Output only transcription text."),
    )
    if thinking is not None:
        d["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking)
    if max_output is not None:
        d["max_output_tokens"] = max_output
    return types.LiveConnectConfig(**d)


def live_cost(model: str, d: dict) -> float:
    price = {"gemini-3.8-live": (3.0, 0.75, 4.5, 12.0),
             "gemini-3.5-transcribe-live": (3.5, 3.5, 21.0, 0.0)}[model]
    input_audio = sum(int(x.get("token_count") or 0) for x in d.get("prompt_tokens_details", [])
                      if str(x.get("modality", "")).upper().endswith("AUDIO"))
    input_text = sum(int(x.get("token_count") or 0) for x in d.get("prompt_tokens_details", [])
                     if not str(x.get("modality", "")).upper().endswith("AUDIO"))
    text_out = sum(int(x.get("token_count") or 0) for x in d.get("response_tokens_details", [])
                   if not str(x.get("modality", "")).upper().endswith("AUDIO"))
    audio_out = sum(int(x.get("token_count") or 0) for x in d.get("response_tokens_details", [])
                    if str(x.get("modality", "")).upper().endswith("AUDIO"))
    thought = int(d.get("thoughts_token_count") or 0)
    if not d.get("response_tokens_details"):
        text_out = max(0, int(d.get("response_token_count") or 0) - thought)
    return (input_audio * price[0] + input_text * price[1] +
            (text_out + thought) * price[2] + audio_out * price[3]) / 1e6


def percentile(values: list[float], q: float) -> float | None:
    return round(float(np.percentile(values, q)), 3) if values else None


def mono(rows: list[dict]) -> list[dict]:
    return [{**r, "speaker": "one"} for r in rows]


def dropped_passages(reference: list[dict], hypothesis: list[dict]) -> list[dict]:
    """Coalesce 1 s reference-speech buckets with no hypothesis words within +/-3 s."""
    missing: set[int] = set()
    for r in reference:
        if not str(r.get("text", "")).strip():
            continue
        for second in range(math.floor(r["start"]), math.ceil(r["end"])):
            if not any(h["end"] >= second - 3 and h["start"] <= second + 4
                       for h in hypothesis if str(h.get("text", "")).strip()):
                missing.add(second)
    out = []
    for second in sorted(missing):
        if out and out[-1]["end"] == second:
            out[-1]["end"] += 1
        else:
            out.append({"start": second, "end": second + 1})
    return out


def reference_speech_seconds(reference: list[dict]) -> int:
    return len({s for r in reference if str(r.get("text", "")).strip()
                for s in range(math.floor(r["start"]), math.ceil(r["end"]))})


async def run_live(args, clip):
    pcm = read_wav(clip.audio)
    source_s = len(pcm) / RATE
    if args.tail_silence:
        pcm = np.concatenate((pcm, np.zeros(round(args.tail_silence * RATE), dtype=np.int16)))
    model = MODEL[args.arm]
    t0 = time.monotonic()
    sent = 0
    event_rows: list[dict] = []
    update_rows: list[dict] = []
    usage_rows: list[dict] = []
    errors: list[str] = []
    resumption: list[dict] = []
    last_text_end = 0.0
    last_final_text = ""
    stop = asyncio.Event()

    async with client().aio.live.connect(model=model, config=live_config(
        args.arm, args.turn, args.sensitivity, args.silence_ms, args.thinking, args.max_output,
        language_code=getattr(args, "language_code", "en"))) as session:
        t0 = time.monotonic()  # connect() has already consumed setup_complete

        async def receive():
            nonlocal last_text_end, last_final_text
            try:
                while True:
                  async for msg in session.receive():
                    when = time.monotonic() - t0
                    sc = msg.server_content
                    row = {"wall_s": round(when, 3), "audio_sent_s": round(sent / RATE, 3)}
                    if msg.setup_complete:
                        row["setup_complete"] = True
                    if msg.go_away:
                        row["go_away"] = msg.go_away.model_dump(exclude_none=True, mode="json")
                    if msg.session_resumption_update:
                        update = msg.session_resumption_update.model_dump(exclude_none=True, mode="json")
                        safe = {"resumable": update.get("resumable"),
                                "has_handle": bool(update.get("new_handle")),
                                "last_consumed_client_message_index": update.get("last_consumed_client_message_index")}
                        resumption.append(safe)
                        row["resumption"] = safe
                    if msg.usage_metadata:
                        d = msg.usage_metadata.model_dump(exclude_none=True, mode="json")
                        usage_rows.append(d)
                        row["usage"] = d
                    if sc:
                        row["turn_complete"] = sc.turn_complete
                        row["generation_complete"] = sc.generation_complete
                        row["waiting_for_input"] = sc.waiting_for_input
                        for field in ("interim_input_transcription", "input_transcription"):
                            tr = getattr(sc, field)
                            if tr:
                                d = tr.model_dump(exclude_none=True, mode="json")
                                row[field] = d
                                txt = (tr.text or "").strip()
                                if txt:
                                    update_rows.append({"kind": field, "text": txt, "audio_start_s": round(last_text_end, 3),
                                                        "audio_end_s": round(sent / RATE, 3), "wall_s": round(when, 3),
                                                        "final": bool(tr.finished)})
                                    if field == "input_transcription":
                                        last_text_end = sent / RATE
                        if sc.model_turn:
                            parts = []
                            audio_bytes = 0
                            for p in sc.model_turn.parts or []:
                                if p.text:
                                    parts.append(p.text)
                                if p.inline_data and p.inline_data.data:
                                    audio_bytes += len(p.inline_data.data)
                            if audio_bytes:
                                row["model_audio_bytes"] = audio_bytes
                            if parts:
                                txt = " ".join(parts).strip()
                                row["model_text"] = txt
                                if txt != last_final_text:
                                    update_rows.append({"kind": "model_text", "text": txt, "audio_start_s": round(last_text_end, 3),
                                                        "audio_end_s": round(sent / RATE, 3), "wall_s": round(when, 3),
                                                        "final": bool(sc.turn_complete)})
                                    last_final_text = txt
                    if len(row) > 2:
                        event_rows.append(row)
                        if not args.quiet:
                            print(json.dumps({"event": row}), flush=True)
            except Exception as exc:
                errors.append(f"receive: {type(exc).__name__}: {str(exc)[:400]}")
            finally:
                stop.set()

        receiver = asyncio.create_task(receive())
        if args.turn:
            await session.send_realtime_input(activity_start=types.ActivityStart())
        for i in range(0, min(len(pcm), int(args.limit * RATE) if args.limit else len(pcm)), FRAME):
            if stop.is_set():
                errors.append(f"socket stopped before frame at {i/RATE:.3f}s")
                break
            due = t0 + i / RATE
            await asyncio.sleep(max(0, due - time.monotonic()))
            chunk = pcm[i:i + FRAME]
            try:
                await session.send_realtime_input(audio=types.Blob(data=chunk.tobytes(), mime_type="audio/pcm;rate=16000"))
                sent += len(chunk)
                if args.turn and sent / RATE >= math.ceil((i / RATE + 0.001) / args.turn) * args.turn - 0.001:
                    await session.send_realtime_input(activity_end=types.ActivityEnd())
                    await session.send_realtime_input(activity_start=types.ActivityStart())
            except Exception as exc:
                errors.append(f"send: {type(exc).__name__}: {str(exc)[:400]}")
                break
        if args.turn:
            try:
                await session.send_realtime_input(activity_end=types.ActivityEnd())
            except Exception as exc:
                errors.append(f"end: {type(exc).__name__}: {str(exc)[:400]}")
        else:
            try:
                await session.send_realtime_input(audio_stream_end=True)
            except Exception as exc:
                errors.append(f"end: {type(exc).__name__}: {str(exc)[:400]}")
        await asyncio.sleep(args.drain)
        receiver.cancel()
        try:
            await receiver
        except asyncio.CancelledError:
            pass

    # The final input-transcription events are the W1/W2 candidate. W3 can also expose model text.
    selected = [u for u in update_rows if u["kind"] == "input_transcription"]
    if args.arm == "w3" and not selected:
        selected = [u for u in update_rows if u["kind"] == "model_text"]
    hyp = [{"start": u["audio_start_s"], "end": max(u["audio_end_s"], u["audio_start_s"] + 0.001),
            "speaker": "one", "text": u["text"]} for u in selected]
    ref = mono(clip.reference_segments())
    lat = [u["wall_s"] - u["audio_end_s"] for u in selected]
    costs = [live_cost(model, u) for u in usage_rows]
    # Live usage is usually cumulative; charge latest observation, not the sum.
    cost = max(costs, default=0.0)
    usage_events = [e for e in event_rows if "usage" in e]
    last_usage_audio_s = usage_events[-1]["audio_sent_s"] if usage_events else None
    cost_complete = last_usage_audio_s is not None and last_usage_audio_s >= sent / RATE - 2.0
    result = {"arm": args.arm, "model": model, "clip": clip.clip_id,
              "language_code": getattr(args, "language_code", "en"), "audio_s": round(len(pcm) / RATE, 3),
              "source_audio_s": source_s, "tail_silence_s": args.tail_silence,
              "sent_s": round(sent / RATE, 3), "events": len(event_rows), "updates": len(update_rows),
              "model_audio_bytes": sum(e.get("model_audio_bytes", 0) for e in event_rows),
              "selected_updates": len(selected), "latency_p50_s": percentile(lat, 50),
              "latency_p90_s": percentile(lat, 90), "latency_max_s": max(lat, default=None),
              "score": score(ref, hyp) if hyp else None,
              "dropped_passages": dropped_passages(ref, hyp),
              "dropped_reference_seconds": sum(x["end"] - x["start"] for x in dropped_passages(ref, hyp)),
              "reference_speech_seconds": reference_speech_seconds(ref), "cost_usd": round(cost, 6),
              "cost_meeting_hour_usd": round(cost / (sent / RATE) * 3600, 4) if sent else None,
              "resumption_updates": resumption, "usage_observations": len(usage_rows), "errors": errors,
              "last_usage_audio_s": last_usage_audio_s, "cost_complete": cost_complete,
              "hypothesis": hyp, "updates_full": update_rows, "events_full": event_rows}
    ledger("P52", {"kind": "live", "model": model, "arm": args.arm, "clip": clip.clip_id,
                   "audio_s": sent / RATE, "cost_usd": cost, "errors": errors,
                   "usage": usage_rows[-1] if usage_rows else {}})
    return result


async def run_batch(args, clip):
    """Submit the latest L seconds every S seconds at 1.0x wall pace."""
    pcm = read_wav(clip.audio)
    duration = min(len(pcm) / RATE, args.limit or len(pcm) / RATE)
    t0 = time.monotonic()
    tasks = []
    sem = asyncio.Semaphore(3)

    async def one(end_s: float):
        start_s = max(0.0, end_s - args.window)
        async with sem:
            started = time.monotonic() - t0
            try:
                result = await asyncio.to_thread(
                    diarize_window, pcm[round(start_s * RATE):round(end_s * RATE)],
                    diarize=False, use_cache=False, max_attempts=3, ledger_lane="P52")
                arrival = time.monotonic() - t0
                return {"window_start_s": start_s, "window_end_s": end_s,
                        "started_s": started, "arrival_s": arrival,
                        "cached": result.cached, "latency_s": result.latency_s,
                        "usage": result.usage, "cost_usd": result.cost_usd(),
                        "timing_anomalies": result.timing_anomalies or {"clamped": 0, "dropped": 0},
                        "words": [{"text": w.text, "start": start_s + w.start, "end": start_s + w.end}
                                  for w in result.words], "error": None}
            except Exception as exc:
                return {"window_start_s": start_s, "window_end_s": end_s,
                        "started_s": started, "arrival_s": time.monotonic() - t0,
                        "words": [], "error": f"{type(exc).__name__}: {str(exc)[:300]}"}

    end_s = float(args.stride)
    while end_s <= duration + 1e-6:
        await asyncio.sleep(max(0, t0 + end_s - time.monotonic()))
        tasks.append(asyncio.create_task(one(end_s)))
        end_s += args.stride
    if duration % args.stride:
        await asyncio.sleep(max(0, t0 + duration - time.monotonic()))
        tasks.append(asyncio.create_task(one(duration)))
    windows = sorted(await asyncio.gather(*tasks), key=lambda x: x["arrival_s"])
    words = []
    watermark = 0.0
    for w in windows:
        newly_seen = []
        for word in sorted(w["words"], key=lambda x: x["start"]):
            if word["end"] > watermark + 0.05 and word["start"] >= watermark - 0.15:
                newly_seen.append({**word, "arrival_s": w["arrival_s"]})
        if newly_seen:
            watermark = max(x["end"] for x in newly_seen)
            words.extend(newly_seen)
        w["new_words"] = len(newly_seen)
        if not args.quiet:
            print(json.dumps({"window": w}), flush=True)
    hyp = [{"start": max(0, w["start"]), "end": max(w["start"] + 0.001, w["end"]),
            "speaker": "one", "text": w["text"]} for w in words]
    ref = mono(clip.reference_segments())
    lat = [w["arrival_s"] - w["end"] for w in words]
    cost = sum(w.get("cost_usd", 0) for w in windows if not w.get("cached"))
    anomaly_calls = sum(any(v for v in w.get("timing_anomalies", {}).values()) for w in windows)
    clamped = sum(w.get("timing_anomalies", {}).get("clamped", 0) for w in windows)
    dropped_offsets = sum(w.get("timing_anomalies", {}).get("dropped", 0) for w in windows)
    return {"arm": "w4", "clip": clip.clip_id, "audio_s": duration, "window_s": args.window,
            "stride_s": args.stride, "windows": len(windows), "window_errors": sum(bool(w["error"]) for w in windows),
            "timing_anomaly_calls": anomaly_calls, "timing_anomaly_call_rate": anomaly_calls / len(windows) if windows else None,
            "timing_clamped_words": clamped, "timing_dropped_words": dropped_offsets,
            "cached_windows": sum(bool(w.get("cached")) for w in windows), "selected_words": len(words),
            "latency_p50_s": percentile(lat, 50), "latency_p90_s": percentile(lat, 90),
            "latency_max_s": max(lat, default=None), "score": score(ref, hyp) if hyp else None,
            "dropped_passages": dropped_passages(ref, hyp),
            "dropped_reference_seconds": sum(x["end"] - x["start"] for x in dropped_passages(ref, hyp)),
            "reference_speech_seconds": reference_speech_seconds(ref), "cost_usd": round(cost, 6),
            "cost_meeting_hour_usd": round(cost / duration * 3600, 4),
            "hypothesis": hyp, "words_full": words, "windows_full": windows}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", choices=["w1", "w2", "w3", "w4"], required=True)
    p.add_argument("--language-code", choices=["en", "en-US", "auto"], default="en")
    p.add_argument("--clip", default="mono_javier_intro_50s")
    p.add_argument("--turn", type=int, default=0)
    p.add_argument("--window", type=int, choices=[8, 15], default=8)
    p.add_argument("--stride", type=int, choices=[2, 3], default=2)
    p.add_argument("--sensitivity", choices=["high", "low"], default="high")
    p.add_argument("--silence-ms", type=int, default=500)
    p.add_argument("--thinking", type=int)
    p.add_argument("--max-output", type=int)
    p.add_argument("--limit", type=float, default=0.0)
    p.add_argument("--tail-silence", type=float, default=0.0)
    p.add_argument("--drain", type=float, default=8.0)
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    clip = next((c for c in clips() if c.clip_id == args.clip), None)
    if clip is None:
        p.error("unknown clip")
    result = asyncio.run(run_batch(args, clip) if args.arm == "w4" else run_live(args, clip))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    if args.quiet:
        summary = {k: v for k, v in result.items() if k not in ("hypothesis", "words_full", "windows_full", "updates_full", "events_full")}
        print(json.dumps({"result": summary, "lane_spend": spend("P52")}, indent=2), flush=True)
    else:
        print(json.dumps({"result": result, "lane_spend": spend("P52")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
