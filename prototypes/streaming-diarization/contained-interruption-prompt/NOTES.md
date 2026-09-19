# Prompt-only contained-interruption falsifier

**THROWAWAY PROTOTYPE — no production prompt change.**

## Structural contract

- **Question:** does the unchanged model omit simultaneous speech because the default output
  contract never explicitly asks for overlapping voices?
- **Minimum primitives:** identical retained audio, default prompt, one fixed generic variant,
  source-aligned interruption evidence, and a clean one-speaker negative control.
- **Invariants:** same endpoint/model, greedy decoding, token cap, parser, and audio bytes; no
  expected names, words, timestamps, or per-case hints in the variant; raw response saved after
  every call; no production edits.
- **Unknown:** whether prompting can expose speech already present in the model's acoustic
  representation.
- **Falsifier:** reject if both overlap arms still omit the source turn, sequential recognition is
  lost, outer-only invents a second speaker/turn, or outer-only word error rate worsens by more than
  0.01 absolute against the paired default call.
- **Tool decision:** five leased calls, peak one, no retries. One default outer reacquisition is
  necessary because the previous harness lost its raw response; retained defaults cover sequential,
  0 dB, and +3 dB. Four calls then apply exactly one fixed prompt variant.

## Frozen prompt variant

The production `DEFAULT_PROMPT` bytes are unchanged. The prototype appends exactly:

```text
如果音频中有清晰可闻的短暂语音或多人同时说话，请转写每位说话人的可听内容；允许不同说话人的时间范围重叠。不要猜测或补充听不清的内容。
```

English gloss for review only: preserve clearly audible brief or simultaneous speech from each
speaker; overlapping time intervals are allowed; do not guess or add unclear content.

## Frozen matrix

1. Default prompt × outer-only (paired negative baseline reacquisition).
2. Variant × outer-only (negative control).
3. Variant × sequential control (positive audibility/control).
4. Variant × retained 0 dB overlap.
5. Variant × retained +3 dB overlap.

The retained default sequential/0 dB/+3 dB raw responses are consumed from
`../contained-interruption/source-backed/results.json`. A positive result needs source-matching
BOSS words on a non-dominant local speaker whose interval intersects 20.00–21.44 s in at least one
true-overlap arm, with both controls green. A new label without source-matching words is a
hallucination.

Dry-run now, without a decoder request:

```bash
PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/contained-interruption-prompt/probe.py
```

Executed once under the identity-only lease:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/contained-interruption-prompt/probe.py \
  --execute --endpoint http://127.0.0.1:19135/v1 --lease-limit 983
```

## Result

**REJECTED.** The generic output-contract change did not recover the contained interruption.

- Requests: global 977→982, five serial calls, peak one for this run, no retries. The sixth
  authorized call was not used.
- Clean outer-only control: one speaker under default and variant; no interruption text invented;
  ordered word error rate stayed 0.097345 (delta 0.000000).
- Sequential control: both default and variant emitted the exact nine-word source turn, `How long
  do we think each one will take?`, as the non-dominant `S02`. Variant timing was 20.20–21.48 s.
- True overlap at 0 dB and +3 dB: both variant outputs remained one-speaker `S01`; neither emitted
  a source-matching non-dominant turn. This is unchanged from the retained default outputs.

All five safety/audibility controls pass, but recovery is false in 0/2 overlap arms. The omission
therefore persists despite an explicit generic overlap instruction. On this source-backed matrix,
the limiting seam is the current decoder/model path, not merely the default prompt contract.

No production prompt or transcript architecture change is supported. `results.json` retains every
raw response; `analysis.json` retains the adjudication. The lease was explicitly released at global
982 with active zero.
