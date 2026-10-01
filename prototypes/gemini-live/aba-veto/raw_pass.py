"""PROTOTYPE — raw-label pass for rule V over the 8 public synthetic meetings (contract: NOTES.md).

  fetch     one production provider call per meeting (the ONLY step that spends); raw responses are saved
  evaluate  $0: replay the saved words through the production TerminalTranscriber under rules A / B / V

PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r4-n.venv/bin/python prototypes/gemini-live/aba-veto/raw_pass.py fetch|evaluate
"""
from __future__ import annotations

import collections
import hashlib
import json
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus import clips  # noqa: E402
from score import score  # noqa: E402
from v_rule import RulePolicy, S, word_turns  # noqa: E402
from moss_transcribe_diarize.app.gemini_file_runner import _WavTape  # noqa: E402
from moss_transcribe_diarize.app.gemini_final_policy import FinalWordPolicy, WebRtcWordGate  # noqa: E402
from moss_transcribe_diarize.app.gemini_lane_engine import WebRtcSpeechDetector  # noqa: E402
from moss_transcribe_diarize.app.gemini_long_final import LongFinalStitcher, _cosine  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import (  # noqa: E402
    GeminiWords, TerminalTranscriber, WindowDiarizer, parse_words, repair_word_timestamps)
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder  # noqa: E402

OUT = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P69/r4-long/bench-aba"
RAW = OUT / "raw"
KEY_FILE = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-r4-int/.env.local")
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
CAP_USD = .45
DER_MARGIN = .005


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def pcm_of(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, S)
        return w.readframes(w.getnframes())


def raw_path(clip_id: str) -> Path:
    return RAW / (clip_id.replace(":", "_") + ".json")


class Recording:
    """Client proxy: the production WindowDiarizer makes the call; this keeps the raw response."""

    def __init__(self, client):
        self._client = client
        self.responses = []
        self.interactions = self

    def create(self, **kwargs):
        response = self._client.interactions.create(**kwargs)
        self.responses.append(response.model_dump(exclude_none=True, mode="json"))
        return response


def fetch() -> None:
    from moss_transcribe_diarize.app.phase2_web_cli import _gemini_client
    key = next(line.split("=", 1)[1].strip() for line in KEY_FILE.read_text().splitlines()
               if line.startswith("GEMINI_API_KEY="))
    RAW.mkdir(parents=True, exist_ok=True)
    ledger_path = OUT / "raw-spend.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.is_file() else {"cap_usd": CAP_USD, "calls": []}
    for clip in clips("synth"):
        target = raw_path(clip.clip_id)
        if target.is_file():
            print(f"have {clip.clip_id}", flush=True)
            continue
        pcm = pcm_of(clip.audio)
        audio_s = len(pcm) / 2 / S
        spent = sum(c["with_output_usd"] for c in ledger["calls"])
        estimate = audio_s / 60 * .005
        if spent + estimate > CAP_USD:
            print(f"STOP before {clip.clip_id}: spent {spent:.4f} + {estimate:.4f} > cap {CAP_USD}", flush=True)
            break
        reports = []
        proxy = Recording(_gemini_client(key))
        diarizer = WindowDiarizer(proxy, lambda **usage: reports.append(usage), max_attempts=2)
        started = time.monotonic()
        failure = None
        try:
            diarizer.diarize(pcm, deadline=time.monotonic() + 240, kind="terminal")
        except Exception as exc:  # recorded; the ledger still counts every attempt
            failure = type(exc).__name__
        metered = sum(float(r.get("cost_usd") or 0) for r in reports)
        output_estimate = sum(float(r.get("output_cost_estimate_usd") or 0) for r in reports)
        call = {"clip": clip.clip_id, "audio_s": audio_s, "attempts": len(reports), "failure": failure,
                "error_codes": [r["error_code"] for r in reports if r.get("error_code")],
                "metered_usd": metered, "output_estimate_usd": output_estimate,
                "with_output_usd": metered - sum(float(r.get("metered_output_usd") or 0) for r in reports) + output_estimate,
                "latency_s": round(time.monotonic() - started, 2), "utc": utc()}
        ledger["calls"].append(call)
        ledger["with_output_usd"] = sum(c["with_output_usd"] for c in ledger["calls"])
        ledger["metered_usd"] = sum(c["metered_usd"] for c in ledger["calls"])
        ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
        if failure is None and proxy.responses:
            target.write_text(json.dumps({"clip": clip.clip_id, "audio": str(clip.audio), "audio_s": audio_s,
                                          "pcm_sha256": hashlib.sha256(pcm).hexdigest(), "fetched_utc": utc(),
                                          "model": diarizer.model, "response": proxy.responses[-1]}) + "\n")
        print(json.dumps({k: call[k] for k in ("clip", "audio_s", "attempts", "failure", "with_output_usd", "latency_s")}),
              flush=True)
    print(json.dumps({"with_output_usd": ledger.get("with_output_usd"), "metered_usd": ledger.get("metered_usd"),
                      "calls": len(ledger["calls"])}), flush=True)


class SavedWords:
    """Stub diarizer: the saved response through the production parse + timestamp repair (kind=terminal)."""

    def __init__(self, response: dict):
        self.response = response

    def diarize(self, pcm16: bytes, *, deadline: float, kind: str = "rolling", diarize: bool = True) -> GeminiWords:
        parsed = parse_words(self.response, audio_samples=len(pcm16) // 2)
        fixed, _repaired = repair_word_timestamps(parsed.words, len(pcm16) // 2)
        return GeminiWords(fixed, parsed.clamped, parsed.dropped)


class CountingEncoder:
    def __init__(self, real):
        self.real, self.intervals = real, 0

    def embed_intervals(self, path, intervals):
        self.intervals += len(intervals)
        return self.real.embed_intervals(path, intervals)


def dominant(words, truth):
    """label -> (dominant true speaker, purity) by word-time overlap with truth segments."""
    seconds: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for w in words:
        a, b = w.start_sample / S, w.end_sample / S
        for r in truth:
            if r["end"] <= a:
                continue
            if r["start"] >= b:
                break
            seconds[w.speaker][r["speaker"]] += min(b, r["end"]) - max(a, r["start"])
    out = {}
    for label, per in seconds.items():
        top, value = per.most_common(1)[0]
        out[label] = (top, round(value / sum(per.values()), 3))
    return out


def evaluate() -> None:
    real = _identity_encoder(LiveProviderBundleConfig.from_manifest(MANIFEST), interval_workers=3)
    results = []
    for clip in clips("synth"):
        source = raw_path(clip.clip_id)
        if not source.is_file():
            results.append({"clip": clip.clip_id, "status": "not fetched"})
            continue
        saved = json.loads(source.read_text())
        truth = sorted(clip.reference_segments(), key=lambda r: r["start"])
        tape = _WavTape(clip.audio)
        row = {"clip": clip.clip_id, "truth": clip.true_speakers, "audio_s": saved["audio_s"]}
        raw_words = SavedWords(saved["response"]).diarize(tape.read(), deadline=0, kind="terminal").words
        row["raw_labels"] = len({w.speaker for w in raw_words})
        row["words"] = len(raw_words)
        per_rule = {}
        for rule in ("shipped", "A", "B", "V"):
            encoder = CountingEncoder(real)
            policy = FinalWordPolicy(encoder) if rule == "shipped" else RulePolicy(encoder, rule)
            terminal = TerminalTranscriber(SavedWords(saved["response"]), identity_policy=policy,
                                           stitcher=LongFinalStitcher(encoder), word_gate=WebRtcWordGate(),
                                           voiced_audio=WebRtcSpeechDetector())
            segments = terminal.transcribe(tape)
            rows = [{"start": s.start_sample / S, "end": s.end_sample / S, "speaker": s.speaker, "text": s.text}
                    for s in segments if s.text.strip()]
            m = score(truth, rows, with_text=False)
            per_rule[rule] = {"der": m["der"], "confusion": m["speaker_confusion"], "miss": m["miss"],
                              "groups": len({r["speaker"] for r in rows}), "encoder_intervals": encoder.intervals,
                              "_rows": [(r["start"], r["end"], r["speaker"]) for r in rows]}
            if rule != "shipped":
                veto = policy.last_veto
                per_rule[rule]["veto_check_embeddings"] = veto.embeddings if veto else 0
                per_rule[rule]["_member"] = dict(policy.last_member) if veto else {}
                per_rule[rule]["_veto"] = veto
                per_rule[rule]["_centroids"] = policy.last_centroids if veto else {}
                per_rule[rule]["_words"] = policy.last_words
        row["A_equals_shipped"] = per_rule["A"]["_rows"] == per_rule["shipped"]["_rows"]
        truth_of = dominant(per_rule["A"]["_words"], truth)  # labels as the policy sees them (terminal-NNNN)
        member_a, member_v, member_b = (per_rule[r]["_member"] for r in ("A", "V", "B"))
        veto_a, veto_v = per_rule["A"]["_veto"], per_rule["V"]["_veto"]
        centroids = per_rule["A"]["_centroids"]
        pairs = []
        labels = sorted(centroids)
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                cosine = _cosine(centroids[a], centroids[b])
                alternations = len(veto_a.alternations.get((a, b), ())) if veto_a else 0
                if cosine < .65 and not alternations:
                    continue
                ta, tb = truth_of.get(a), truth_of.get(b)
                relation = "unknown" if ta is None or tb is None else ("same" if ta[0] == tb[0] else "different")
                if cosine < .65:
                    continue
                pairs.append({"labels": [a, b], "cosine": round(cosine, 3), "alternations": alternations,
                              "truth_relation": relation, "truth": [ta, tb],
                              "veto_stands_under_V": bool(veto_v.genuine((a, b))) if alternations else None,
                              "merged_A": member_a.get(a) == member_a.get(b),
                              "merged_B": member_b.get(a) == member_b.get(b),
                              "merged_V": member_v.get(a) == member_v.get(b)})
        row["pairs_cos_ge_65"] = pairs
        for rule in ("B", "V"):
            member = per_rule[rule]["_member"]
            new = []
            for i, a in enumerate(labels):
                for b in labels[i + 1:]:
                    if member.get(a) == member.get(b) and member_a.get(a) != member_a.get(b):
                        ta, tb = truth_of.get(a), truth_of.get(b)
                        new.append({"labels": [a, b], "cosine": round(_cosine(centroids[a], centroids[b]), 3),
                                    "truth_relation": "unknown" if ta is None or tb is None else
                                    ("same" if ta[0] == tb[0] else "different"), "truth": [ta, tb]})
            per_rule[rule]["new_merges_vs_A"] = new
        row["protected_pairs_under_A"] = [p for p in pairs if p["truth_relation"] == "different" and not p["merged_A"]]
        row["single_alternation_protected"] = [p for p in row["protected_pairs_under_A"] if p["alternations"] == 1]
        if veto_v is not None:
            row["V_alternations_checked"] = {
                " / ".join(pair): {"alternations": len(seen), "stands": veto_v._genuine.get(pair)}
                for pair, seen in veto_v.alternations.items() if pair in veto_v._genuine}
        row["rules"] = {rule: {k: v for k, v in data.items() if not k.startswith("_")}
                        for rule, data in per_rule.items()}
        results.append(row)
        print(json.dumps({"clip": row["clip"], "truth": row["truth"], "raw_labels": row["raw_labels"],
                          "A=shipped": row["A_equals_shipped"],
                          **{r: (row["rules"][r]["groups"], row["rules"][r]["der"]) for r in ("A", "B", "V")},
                          "V_new": row["rules"]["V"]["new_merges_vs_A"], "B_new": row["rules"]["B"]["new_merges_vs_A"],
                          "protected": len(row["protected_pairs_under_A"]),
                          "single_alt_protected": len(row["single_alternation_protected"]),
                          "V_veto_embeddings": row["rules"]["V"]["veto_check_embeddings"]}), flush=True)
    done = [r for r in results if "rules" in r]
    gates = {}
    for rule in ("B", "V"):
        false_merges = [{"clip": r["clip"], **m} for r in done for m in r["rules"][rule]["new_merges_vs_A"]
                        if m["truth_relation"] == "different"]
        worse = [{"clip": r["clip"], "A": r["rules"]["A"]["der"], rule: r["rules"][rule]["der"]} for r in done
                 if r["rules"][rule]["der"] - r["rules"]["A"]["der"] > DER_MARGIN]
        away = [{"clip": r["clip"], "truth": r["truth"], "A": r["rules"]["A"]["groups"], rule: r["rules"][rule]["groups"]}
                for r in done if abs(r["rules"][rule]["groups"] - r["truth"]) > abs(r["rules"]["A"]["groups"] - r["truth"])]
        protected = [{"clip": r["clip"], **p} for r in done for p in r["protected_pairs_under_A"]]
        gates[rule] = {"protection": {"exercised": bool(protected), "protected_pairs": len(protected),
                                      "single_alternation_protected_pairs": sum(1 for p in protected if p["alternations"] == 1),
                                      "k4_s0_protected_pairs": [p for p in protected if p["clip"] == "synth:meet_k4_s0"],
                                      "new_different_speaker_merges": false_merges,
                                      "pass": bool(protected) and not false_merges},
                       "no_harm_fresh": {"worse": worse, "moved_away": away, "pass": not worse and not away}}
    (OUT / "raw-results.json").write_text(json.dumps({"schema": "aba-veto-raw.v1", "der_margin": DER_MARGIN,
                                                      "fetched": len(done), "gates": gates, "clips": results},
                                                     indent=1) + "\n")
    print(json.dumps({"fetched": len(done),
                      "gates": {rule: {k: v["pass"] for k, v in g.items()} for rule, g in gates.items()}}), flush=True)


if __name__ == "__main__":
    {"fetch": fetch, "evaluate": evaluate}[sys.argv[1]]()
