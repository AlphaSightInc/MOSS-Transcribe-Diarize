"""The production provider client with every raw answer written once and replayed for identical request bytes.

R5-D's recorded answers are read in place and never written; new answers go under the f2 evidence folder, and
only when `record` is set (ledger first). (throwaway)
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import ledger

S = 16000
RAWS = [ledger.EV / "provider-responses", ledger.D_EV / "provider-responses"]     # mine (written), R5-D's (read)


def recorded(pattern: str) -> list[Path]:
    return [path for raw in RAWS for path in sorted(raw.glob(pattern))]


def tab_digests() -> set[str]:
    """Requests of R5-D's shared tab lane: the digests two R5-D runs with different microphones have in common."""
    def digests(run):
        receipt = ledger.D_EV / "runs" / run / "receipt.json"
        return {call["digest"] for call in json.loads(receipt.read_text())["batch_calls"]}
    return digests("rp-listen-aec40") & digests("rp-short-noecho")


class Client:
    def __init__(self, answers: str, *, record: bool = False, donor: str | None = None, real_client=None):
        self.interactions = self
        self.answers, self.record, self.donor = answers, record, donor
        self._real_client, self._real = real_client, None
        self.calls: list[dict] = []
        self._tab = tab_digests() if donor else set()

    def _client(self):
        if self._real is None:
            if self._real_client is None:
                from moss_transcribe_diarize.app.phase2_web_cli import _gemini_client as real
            else:
                real = self._real_client
            self._real = real(os.environ.get("GEMINI_API_KEY"))
        return self._real

    def create(self, *, model, input, generation_config):  # noqa: A002
        digest = hashlib.sha256((input[0]["data"] + json.dumps(generation_config, sort_keys=True) + model)
                                .encode()).hexdigest()[:16]
        repeat = sum(1 for call in self.calls if call["digest"] == digest)
        seconds = (len(input[0]["data"]) * 3 // 4 - 44) / (2 * S)
        found = recorded(f"*-{digest}-{repeat}.json") or recorded(f"*-{digest}-*.json")
        call = {"digest": digest, "seconds": seconds, "replayed": bool(found) and found[0].name}
        self.calls.append(call)
        if not found and self.donor is not None:
            for path in recorded(f"{self.donor}-*-*.json"):
                answer = json.loads(path.read_text())
                if path.name.split("-")[-2] not in self._tab and abs(answer["audio_seconds"] - seconds) < 0.01:
                    call["replayed"] = f"donor:{path.name}"
                    found = [path]
                    break
        if not found:
            if not self.record:
                raise RuntimeError(f"replay: no recorded response for request {digest} ({seconds:.0f} s)")
            ledger.check(seconds * ledger.BATCH_PER_S, f"{self.answers} batch {seconds:.0f}s")
            response = self._client().interactions.create(model=model, input=input,
                                                          generation_config=generation_config)
            path = RAWS[0] / f"{self.answers}-{digest}-{repeat}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": model, "generation_config": generation_config,
                                        "audio_seconds": seconds,
                                        "response": response.model_dump(exclude_none=True, mode="json")},
                                       ensure_ascii=False, indent=1))
            ledger.add(f"batch {self.answers} {digest}", seconds * ledger.BATCH_PER_S, seconds=seconds,
                       basis="with_output_estimate")
            call["paid"] = True
            found = [path]
        data = json.loads(found[0].read_text())["response"]
        return type("Response", (), {"model_dump": lambda self, **_k: data})()


def w3_file(name: str | None) -> Path | None:
    return next((raw / f"{name}-w3.json" for raw in RAWS if (raw / f"{name}-w3.json").is_file()), None) if name else None
