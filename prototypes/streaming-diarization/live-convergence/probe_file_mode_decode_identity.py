"""Print what the file pipeline's decoder returns for a fixed set of answers.

Run once against the working tree and once against a checkout of HEAD; the two JSON
documents must be identical. `elapsed_sec` is excluded because it is a measurement of this
process, not of the code under comparison.
"""
import json, sys, tempfile
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo))
import numpy as np, soundfile as sf
from moss_transcribe_diarize.app.vllm_runner import VllmRunner

RESPONSES = [
    {"text": "[0.00][S01]hello there[1.10]", "usage": {"prompt_tokens": 11, "completion_tokens": 7}},
    {"text": "[0.00][S01]one[0.50][0.50][S02]two[1.00]", "usage": {"prompt_tokens": 13, "completion_tokens": 19}},
    {"text": "  [0.00][S01]padded[2.50]  ", "usage": {"prompt_tokens": 9, "completion_tokens": 5}},
    {"text": "[0][S01]hello[1]", "usage": {"prompt_tokens": 3, "completion_tokens": 0}},
    {"text": "   ", "usage": {"prompt_tokens": 3, "completion_tokens": 4}},
    {"text": "silence", "usage": {"prompt_tokens": 3, "completion_tokens": 4}},
]

out = []
with tempfile.TemporaryDirectory() as tmp:
    audio = Path(tmp) / "sample.wav"
    sf.write(audio, np.zeros(1600, dtype=np.float32), 16000)
    for response in RESPONSES:
        runner = VllmRunner(base_url="http://vllm.test:8000", model="moss-vllm")
        runner._post_multipart = lambda *a, response=response, **k: response
        try:
            result = runner.transcribe(audio, max_new_tokens=128)
        except Exception as exc:
            out.append({"answer": response["text"], "raised": type(exc).__name__, "message": str(exc).replace(tmp, "<tmp>")})
            continue
        row = result.to_dict()
        row.pop("elapsed_sec", None)
        row["audio"] = "<tmp>/sample.wav"
        out.append({"answer": response["text"], "result": row})
print(json.dumps(out, indent=2, ensure_ascii=False))
