# P74-RS-FIX1 — throwaway R4 measurement

1. **Question:** can a reload before any accepted frame invent a gap on a mixer clock that has not started?
2. **Primitives:** accepted lane cursor (audio admitted even before mixing), mixed samples (audio already emitted), mixer origin (first accepted audio), interruption (missing time after audio). Each identifies a different stage; mixed samples alone cannot detect an accepted single-lane frame.
3. **Invariants:** no accepted audio means late start and no interruption; first accepted frame starts the timeline. Any accepted lane retains the existing gap. Resume authority, fence and lease unchanged; open intervals omitted.
4. **Unknowns:** real devices, providers and network clock accuracy unmeasured. No new policy: implement lead R4.
5. **Falsifier:** late-start metadata overlaps speech or exceeds archive; either single-lane control loses its gap/archive duration; Stop publishes an open interval.
6. **Tools:** unchanged reviewer script establishes the actual saved corruption; in-process copy of the existing route function measures the conditional rule before product edits; real-route tests use existing offline bench plus decoded MP3 to reject timeline changes. Full backend and six product gap cells subsequently qualify candidate compatibility.

Hypothesis: record an interruption only if mixed samples or an accepted lane sequence exist. Lane sequence advances only on admitted new audio; retained PCM can be pruned and mixed samples can still be zero, so neither alone suffices.

One command, from worktree root:
`MOSS_TEST_REAL_SQLITE=1 PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/long-meeting/resume-fix1/run.py --origin-probe`

The candidate uses a process-local copy of attach_live_routes frozen from a6117c0a; no checkout product edit. It runs the unchanged reviewer script (full zero-prefix state printed), then the zero-prefix, both one-lane, original early-resume and open-interval controls. Without --origin-probe it reproduces the intermediate R4-only candidate's retained microphone-control failure. State/audio use disposable evidence/test directories; no server/provider/key. Reviewer script writes its existing receipt as specified. Receipts copied into RS-FIX1 before/after.

Final verdict: PASS at $0; measured history and negative receipts below. This directory is throwaway; candidate product/bench commit hashes are indexed in P74-RS-FIX1-STATUS.md.

## Measured R4 verdict before product edits

Unchanged reviewer: resume/frames/Stop 200; 8000 decoded samples / 0.5 s; speech 0–0.5 s; erroneous interruption 0–80000 samples / 5 s.
Baseline tests: 2 failed, 3 passed. R4 late-start regression fails; original early system frame, system-only archive control and open-interval control pass. The additional microphone-only control FAILS on the baseline: saved archive 8000 rather than 96000 samples, although interruption is 8000–88000. System resumes first in the frozen test, reproducing the lost origin when mixer starts after the peer arrives. This is independent of the R4 metadata conditional.
Process-local candidate: 4 passed, 1 failed. R4 regression becomes green; saved interruption absent, speech 0–0.5 s, archive 8000 samples. The same microphone-only failure remains. No negative result rerun/tuned into a pass; receipts retain both failures. R4 rule passes; broader one-lane control gate is unresolved. Scope clarification requested while completing independent verification.

Receipts: `evidence/P74/RS-FIX1/reviewer-before.txt`, `red-a6117c0a.txt`, `prototype.txt` under the user's moss-gemini folder. No debug instrumentation or source copy persists in product.

## Additional origin hypothesis (prototype only; product scope pending)

Question: can preserving the already accepted prefix origin at resume prevent a new peer from shifting the first mix forward? Minimum primitive is the existing mixer cursor; no larger buffer/new clock. Invariant: only an interruption with prior accepted audio and an uninitialized mixer may seed that cursor from the retained prefix; ordinary and zero-prefix start are unchanged. Unknown: general gap cells until product replay. Falsifier: the same frozen microphone-only control still loses its six-second archive, or existing system/late-start controls change. Tool decision: `run.py --origin-probe` changes only the process-local cursor initialization and runs the SAME five controls. It uses private state only in throwaway code; any product change would need a small mixer method. No existing failed measurement is discarded. No product authorization inferred from this experiment.

Origin-probe verdict: five frozen controls PASS (1.19 s), including microphone-only prefix/system-first resume: exact 96000-sample / 6 s archive with unchanged 8000–88000 interruption. Zero-prefix still has no interruption and exact 8000-sample / 0.5 s archive. Receipt `RS-FIX1/origin-prototype.txt`. This does not yet qualify a broader product change or six-cell compatibility.

## Product scope resolution

The brief explicitly requires interruption/zero-fill after audio was accepted on at least one lane and an audio-plus-gap archive in the one-lane control. That already authorizes preserving the existing unmixed prefix origin; the optional scope question was unnecessary, not a new policy gate. Candidate product now applies the measured origin rule after successful lease renewal using preserve_resume_origin (existing cursor, existing lock; no new clock/buffer). Ordinary and zero-prefix startup are untouched. R4-only full-suite run intentionally interrupted before completion and retained as full-backend-r4-only-incomplete.txt; it is not counted as a suite result. A new full-suite run qualifies the final candidate. Negative baseline and R4-only controls remain retained.

## Final qualification

Frozen-baseline prototype (`--origin-probe`): 5 passed in 1.25 s; receipt origin-prototype-frozen.txt. Product route+mixer: 64 passed in 16.84 s, targeted-final.txt. Mandated full backend: 2961 passed, 9 skipped, 2 xfailed, 27 warnings, 37 subtests passed in 445.96 s, full-backend-final.txt. Original early-system-frame test unchanged; zero-frame and microphone-only controls red -> green; system-only and open-interval controls green before/after. Unchanged reviewer final: no metadata, exact 0.5 s audio/speech, completed, reviewer-final.txt.

All six final product gap cells PASS unchanged in resume/RS-product-20261002-152501/matrix.json: 5/30/90/119 s +4 s => 13/38/98/127 s archive, 16/16 resumed frames, zero interior gap amplitude; 125 s refused (409/interrupted); 119 s +45 s => 168 s, 180/180 frames, 472000/960000 peak samples, 30 s first resumed live row. product-final.txt retains full state. These are offline routes/archive measurements; physical devices, Chrome product recovery, real network clock accuracy, provider and deployed-host behavior remain unmeasured. No local server launched, no provider/key/private-state access, no push.

Recommend lead review of the candidate, including the small origin preservation needed for the microphone-only control; no deployment claim. Estimate ~20 implementation lines; measured source diff 15 insertions / 4 deletions, plus 69 test lines and design text. No new clock/buffer, accepted-Stop lease rule or ordinary startup change. The frozen negative intermediate results remain separate; nothing rerun/tuned into a pass.
