"""Three uncached public Transcribe direct/proxy pairs plus one proxied Live handshake.

Run: python prototypes/gemini-live/stress/probe_google.py --out evidence/P64/proxy-google.json
No cached helper call is used; this issues at most six 4-second batch requests and one
Live setup with no audio. Estimated spend is far below $2. The API key is never logged.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import signal
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))
from corpus import clips  # noqa: E402
from gemini_common import _parse, ledger, load_key, read_wav, wav_bytes  # noqa: E402

MODEL = "gemini-3.5-transcribe"
CONFIG = {"transcription_config": {"mode": {"type": "verbatim", "diarization_mode": "speaker",
                                             "timestamp_granularities": ["word"]}}}
SELECTED = ("interview_bill_ackman_60s", "interview_keyu_jin_60s", "mono_javier_intro_50s")


def canonical_usage(usage: dict) -> dict:
    normalized = dict(usage)
    normalized["input_tokens_by_modality"] = sorted(
        normalized.get("input_tokens_by_modality") or [], key=lambda row: row["modality"])
    return normalized


def call(client, audio: bytes, case_id: str, route: str) -> dict:
    payload = base64.b64encode(audio).decode()
    start = time.monotonic()
    try:
        response = client.interactions.create(model=MODEL,
            input=[{"type": "audio", "data": payload, "mime_type": "audio/wav"}],
            generation_config=CONFIG)
        latency = time.monotonic() - start
        raw = {"model": MODEL, "latency_s": latency, "audio_seconds": 4,
               "response": response.model_dump(exclude_none=True, mode="json")}
        parsed = _parse(raw, cached=False)
        ledger("P64", {"kind": "proxy_probe", "case_id": case_id, "route": route,
                       "model": MODEL, "audio_s": 4, "latency_s": latency,
                       "cost_usd": parsed.cost_usd(), "usage": parsed.usage,
                       "timing_anomalies": parsed.timing_anomalies})
        return {"words": [(w.text, w.speaker, w.start, w.end) for w in parsed.words],
                "usage": parsed.usage, "cost_usd": parsed.cost_usd(),
                "latency_s": round(latency, 3), "anomalies": parsed.timing_anomalies}
    except Exception as exc:
        ledger("P64", {"kind": "error", "case_id": case_id, "route": route,
                       "model": MODEL, "error_type": type(exc).__name__})
        raise


async def live_probe(client) -> dict:
    start = time.monotonic()
    try:
        async with client.aio.live.connect(model="gemini-3.5-transcribe-live",
                                           config=types.LiveConnectConfig(response_modalities=["TEXT"])):
            latency = time.monotonic() - start
        ledger("P64", {"kind": "live_setup_probe", "model": "gemini-3.5-transcribe-live",
                       "audio_s": 0, "latency_s": latency, "cost_usd": 0,
                       "usage_status": "UNMEASURED; no audio sent"})
        return {"connected": True, "setup_latency_s": round(latency, 3),
                "audio_sent_s": 0, "usage": "UNMEASURED"}
    except Exception as exc:
        ledger("P64", {"kind": "error", "model": "gemini-3.5-transcribe-live",
                       "route": "proxy", "error_type": type(exc).__name__})
        return {"connected": False, "error_type": type(exc).__name__}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-route-only", action="store_true",
                        help="one public batch call plus Live setup using SDK environment routing")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("--out must be new")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="p64-google-", dir=os.environ.get("TMPDIR")) as scratch_name:
        scratch = Path(scratch_name)
        cert, key = scratch / "cert.pem", scratch / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log = (scratch / "proxy.log").open("wb")
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("gemini_fault_proxy.py")),
                                    "--port", "18520", "--cert", str(cert), "--key", str(key),
                                    "--log", str(args.out.with_name("proxy-google-faults.jsonl"))],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            for _ in range(50):
                try:
                    with httpx.Client(verify=str(cert), timeout=1) as probe:
                        if probe.get("https://127.0.0.1:18520/__fault/status").status_code == 200:
                            break
                except httpx.HTTPError:
                    time.sleep(.1)
            else:
                raise RuntimeError("proxy startup failed: " + (scratch / "proxy.log").read_text()[-1000:])
            key_value = load_key()
            corpus = {c.clip_id: c for c in clips("accept6")}
            if args.env_route_only:
                os.environ["GOOGLE_GEMINI_BASE_URL"] = "https://127.0.0.1:18520"
                os.environ["SSL_CERT_FILE"] = str(cert)
                env_client = genai.Client(api_key=key_value)
                case_id = SELECTED[0]
                pcm = read_wav(corpus[case_id].audio)[10 * 16000:14 * 16000]
                batch = call(env_client, wav_bytes(pcm), case_id, "env_proxy")
                live = asyncio.run(live_probe(env_client))
                proxy_status = httpx.get("https://127.0.0.1:18520/__fault/status",
                                         verify=str(cert), timeout=5).json()
                result = {"routing": "GOOGLE_GEMINI_BASE_URL + SSL_CERT_FILE",
                          "proxy_counts": proxy_status["counts"],
                          "rest_routed": proxy_status["counts"]["rest"] >= 1,
                          "live_routed": proxy_status["counts"]["ws"] >= 1 and live["connected"],
                          "batch_words": len(batch["words"]), "batch_cost_usd": batch["cost_usd"],
                          "batch_timing_anomalies": batch["anomalies"], "live": live,
                          "cached_calls": 0}
            else:
                direct = genai.Client(api_key=key_value)
                ctx = ssl.create_default_context(cafile=str(cert))
                proxied = genai.Client(api_key=key_value, http_options=types.HttpOptions(
                    base_url="https://127.0.0.1:18520", client_args={"verify": str(cert)},
                    async_client_args={"ssl": ctx}))
                pairs = []
                for case_id in SELECTED:
                    pcm = read_wav(corpus[case_id].audio)[10 * 16000:14 * 16000]
                    if len(pcm) != 4 * 16000:
                        raise RuntimeError("public clip too short")
                    audio = wav_bytes(pcm)
                    a = call(direct, audio, case_id, "direct")
                    b = call(proxied, audio, case_id, "proxy")
                    pairs.append({"case_id": case_id, "direct_words": len(a["words"]),
                                  "proxy_words": len(b["words"]), "word_annotations_equal": a["words"] == b["words"],
                                  "usage_equal": a["usage"] == b["usage"],
                                  "usage_semantically_equal": canonical_usage(a["usage"]) == canonical_usage(b["usage"]),
                                  "direct_cost_usd": a["cost_usd"], "proxy_cost_usd": b["cost_usd"],
                                  "direct_anomalies": a["anomalies"], "proxy_anomalies": b["anomalies"],
                                  "direct_latency_s": a["latency_s"], "proxy_latency_s": b["latency_s"]})
                live = asyncio.run(live_probe(proxied))
                result = {"windows": pairs, "live": live,
                          "batch_spend_usd": round(sum(row["direct_cost_usd"] + row["proxy_cost_usd"]
                                                       for row in pairs), 6),
                          "proxy_pass_through": all(row["word_annotations_equal"] and
                                                    row["usage_semantically_equal"] for row in pairs),
                          "cached_calls": 0}
            args.out.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            log.close()


if __name__ == "__main__":
    main()
