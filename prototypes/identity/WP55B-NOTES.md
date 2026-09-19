# WP55b-P short-speaker feasibility prototype

Status: **COMPLETE — STEP 1 FAIL / STOP-AND-REPORT.**

## Contract

- **Question:** can three complete, pure-source interruption snippets be frozen before
  a new decoder lease?
- **Minimum primitives:** source-owned utterance, exact sample boundary, independent
  speaker ownership, complete words, and absence of adjacent speaker spill.
- **Invariants:** no spill; three valid snippets; no decoder call before step 1 passes;
  no audio playback under the common contract.
- **Unknown:** replacement clip boundaries and acoustic ownership remain unmeasured.
- **Falsifier:** any adjacent source speech, incomplete utterance, or inability to
  perform the required listening adjudication.
- **Tool:** retained manifests/results establish custody and the two known invalid
  clips. No acoustic or decoder tool may substitute for the required source listening.

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
prototypes/identity/short_speaker_adjudication.py
```

## Verdict

**FAIL.** Round 2 retains one useful exact BOSS witness, while ENG_B is contaminated
by adjacent “I’m not” and Lex by “But you're”/“At your.” The brief requires listening
against the sources to freeze replacements, but `COMMON.md` forbids playing audio.
Reference timestamps cannot override demonstrated acoustic spill.

Per the brief, stop here. IP1 CPU ONNX controls were not run; the 12-request oracle
matrix was not unlocked; decoder use is **0/12**. The atomic terminal transaction,
Jamie at 0%, and 0/3 overlap recovery remain blocked exactly as stated in the brief.

Evidence: `short-speaker-results.json` and
`../../evidence/round3/wp55b-p/short-speaker-results.json`.

Fresh verification attempt 1 exposed a deterministic-evidence defect: the result
encoded the moving pane `HEAD`. It now records the fixed candidate SHA, base ancestry,
and unchanged product/test/frontend tree. A rerun again exited 2 with 0/3 snippets and
0 decoder requests.
