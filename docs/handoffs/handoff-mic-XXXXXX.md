# Handoff: the last two attended-capture defects

Written 2026-08-19. `dev` = `88c750d`, pushed to `private`, working tree clean.

Phase 1 capture now works end to end: the operator ran an attended session on their MacBook Pro and
got a live diarized transcript in the browser. **Two quality defects remain**, both found by that
run, both open. Everything else about the capture path is fixed and confirmed by the operator.

## Your two items

### 1. The operator's own voice transcribes almost not at all  ← the real one

From a ~60 s attended run where they spoke continuously, the entire microphone contribution was:

```
S00  00:00:00  嗯。
S00  00:00:17  嗯。
S00  00:00:31  Yes.
S00  00:00:36  Um.
```

while the shared lane produced full paragraphs. **Only short loud interjections survived** — the
signature of a lane buried in the mono mix.

The microphone is not at fault and this is settled, not a hypothesis. A standalone diagnostic
(`ProjectResources/Frontend/mic-check.html`, committed, served at `/static/mic-check.html`) ran
`getUserMedia` with MOSS's exact constraints and then both lanes together in MOSS's own order:

| condition | measured |
|---|---|
| mic, our constraints, echo cancel ON | -20.5 / -20.2 dBFS |
| mic, our constraints, echo cancel OFF | -14.6 / -12.3 dBFS |
| **both lanes together**, speakers | mic **-22.3 dBFS after sharing started** → survived |
| **both lanes together**, headphones | mic **-21.2 dBFS after sharing started** → survived |
| shared lane | -10.7 / -12.8 dBFS, track label `Tab audio` |

So Chrome, macOS, the device and our constraints are all healthy, both lanes coexist, and the shared
lane is genuinely tab audio (an earlier "lanes are swapped" theory is **disproved**).

The mechanism is `live_mixer.py:256`:

```python
mixed = (system * _HEADROOM_GAIN) + (microphone * _HEADROOM_GAIN)
```

Both lanes get the identical fixed gain and there is no level matching. Measured disparity is
**15.377 dB** (loop iteration 20).

**Read this before you touch it.** Iteration 20 tried peer-RMS matching, measured WER **+3.468 pp**
and six more missing words, and rejected it. **That rejection is not safe to rely on** — its fixture
played the *same* audio in both lanes, so matching levels merely sums a signal with itself. The
loop's own notes concede the fixture cannot set a general policy. The real condition is two
*different* speakers, where the quiet lane carries words that exist nowhere else.

`prototypes/lane-balance/` is a bed for exactly that, already written and committed:
`meet_k2_s0.wav` as the shared lane, `meet_k2_s1.wav` attenuated to -15 dB as the microphone lane,
mixed through a faithful copy of the real limiter, scored by how much of each lane's own clean
reference survives. **It has never produced a policy result** — see its `NOTES.md` for why and for
two runtime traps that cost hours. Treat it as a bed, not a finding.

Do not ship a hand-tuned constant. `AGENTS.md` requires measurement before production code, and this
is the exact case it exists for.

### 2. Speaker over-splitting — needs confirming before anything else

In the same transcript, `S01`/`S02` were both a commercial voice-over and `S04`/`S05` were both the
documentary narrator. The operator is unsure whether each pair is one voice split in two or genuinely
two voices. **Confirm before treating it as a defect** — a commercial can legitimately have two
readers.

If real, the seam is the identity album, not the mixer: `live_identity_album.py`,
`live_identity_sweep.py`, and the manifest-tuned `min_match_score` / `min_match_margin` /
`album_admission_seconds` / `birth_min_seconds` (`live_manifest_finalizer.py:104-106`). Note these
are **deploy-manifest values, not code constants** — charter §8.

Be careful not to conflate the two items: burying a lane and splitting a speaker are independent, and
fixing the mix may change diarization inputs enough to confuse a before/after comparison. Measure
them separately.

## How to run the attended stack

```bash
./scripts/moss-vllm-tunnel.sh                    # GPU host's vLLM, idempotent
./scripts/g3-attended-session.sh                 # prints URL + bearer
```

- Inference is **only** ever the GPU host via the tunnel at `http://127.0.0.1:18000/v1`.
  **This Mac must not load the model** — operator ruling, and `scripts/g3-attended-session.sh`
  enforces it with a refusal that has its own tests (`tests/test_g3_attended_session.py`).
- The browser must run on the **M4 MacBook Pro** (that is where the microphone is); the service binds
  `0.0.0.0` and the laptop reaches it at `https://macstudio.tailnet.aisight.us:7861/`.
- Both were up and healthy at handoff.

## Runtime traps, learned the hard way

- **Audio beyond ~12 s never returns** from this deployment. 12 s decodes in ~1.1 s; 25 s and 60 s
  clips hang, and killing the client leaves vLLM still generating, which then queues every later
  request behind it and looks exactly like a dead server. Keep clips short.
- Never `struct.pack("<" + "h" * n, ...)` for PCM. A 192 k-character format string stalls for
  minutes and is indistinguishable from a hung model call. Use `array`.
- The GPU host is **READ-ONLY** (charter §1). vLLM there binds `127.0.0.1` under a
  `systemd --user` unit; tailnet rebinding was tried and **rolled back** because the card has under
  1 GiB free with `mineru-api` holding 0.5 utilisation, and the engine dies on KV cache. The tunnel
  exists precisely so that host is never touched.
- `gh issue list` with no `--repo` hits the **upstream fork parent** `OpenMOSS/...`, not ours. Always
  pass `--repo aiSight-us/MOSS-Transcribe-Diarize`.

## Baseline to protect

pytest **2 failed / 1087 passed / 396 subtests** — both failures are the declared permanent Phase 1
baselines (l15 hash pin, untracked l2-stage0 corpus); never "fix" them. Frontend **130/130** across
17 files, typecheck clean. Rebuild the bundle after any `frontend/src` change and confirm the served
bundle matches the committed one — fixes have twice sat on a branch while the operator tested older
code.

## Fleet

A ralph loop runs in tmux `MOSS:2.2` on `afk5/phase1-completion` in worktree
`~/.treehouse/MOSS-Transcribe-Diarize-e7521b/1/MOSS-Transcribe-Diarize`; a monitor agent in `MOSS:2.1`
steers it via that loop's `context.md` and owns the GitHub board. The monitor has standing authority
to restart the loop but **does not merge to `dev`** — that stayed with the orchestrator deliberately.
Its brief is `scripts/afk5-phase1-completion/MONITOR.md`.

If you work these two items yourself, tell the monitor so the loop does not duplicate you. Its queue
already carries "Defect B replication" (item 1 here) blocked on exactly the dual-lane fixture the
`lane-balance` bed now provides.

## Open, not yours unless you choose

`docs/phase1-gate-status.md` is the authoritative gate rollup — read it rather than re-deriving.
Issues #1, #3, #5, #8, #9 remain open there with the specific criterion each still needs. G4/G5 need
a ≥10-minute concurrency run whose latency figures will include tunnel transit on a GPU shared with
`mineru-api`, which must be stated in the evidence rather than presented as a production bound.

## Suggested skills

- **`/diagnose`** for item 2 first — confirm the over-split is real before spending anything on it.
  Every genuine defect this cycle was found by reproducing rather than reasoning.
- **`/prototype`** for item 1 — extend `prototypes/lane-balance/`, do not rebuild scaffolding. The
  bed, the corpus, the mixer copy and the scoring are done; it needs running and interpreting.
- Skip `/grilling` and `/domain-modeling`; the 12 wayfinder tickets are closed and settled.

## One caution

Four separate attended runs were spent chasing causes that turned out to be wrong — including one
where the previous orchestrator declared the problem environmental and told the fleet not to touch
it, which the operator's own diagnostic then disproved. The operator's observations were right each
time and the interpretation was wrong. When their report and a plausible theory disagree, reproduce
before concluding.
