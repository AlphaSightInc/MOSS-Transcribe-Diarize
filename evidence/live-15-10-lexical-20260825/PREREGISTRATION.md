# Goal 2 preregistration — deployed 15/10 lexical

**Frozen before B1 code and before Goal-2 inference:** 2026-08-25 EDT.

## B0 decision contract

- Signed decision: `D-M2-3 = O2`.
- Changed-region correction ceiling: **15.0 s**, pooled nearest-rank p95.
- Accuracy materiality: **.010000 absolute macro WER**.
- First-publication non-inferiority: **candidate pooled p95 <= fresh control pooled p95 + .500000 s**.
- Reference truth is scorer-only. Production reconciliation and the prototype adapter may not
  read reference files or scores.

The signed record is
`evidence/live-g4-recovery-20260825/D-M2-3.md`, SHA-256
`c8ca376304469de14db5eac6dd48599cd7ce0b3b4f64f49e593b831fca24def6`.

## Frozen sources

Goal-1 drift comparator:

- root: `evidence/live-g4-recovery-20260825/deployed-10-10/`;
- results SHA-256: `ed9813f4009e869f27f4b6171223153a80e9837f361681de0ca11c5c9396e44d`;
- gate SHA-256: `084945d57538e248f0b213e0c74b55b2018740190f50bb2901b602bdf57fd97d`;
- 12 actual-live sessions, six cases x two passes, 1,239.987 observed audio-seconds;
- settled pre-Stop macro WER `.140442`; correction p95 `10.471099 s`; first-publication
  p95 `3.652696 s`.

Goal 1 is a drift diagnostic only. **Promotion compares the fresh ABBA 15/10 candidate against
the fresh ABBA 10/10 control.** Historical shadows are context only.

Corpus:

- root: `evidence/live-policy-sweep-20260825/corpus/`;
- manifest SHA-256:
  `80fc15bd730f7aa44d8a69aa6e7e00aaf43ed54e2af8a03abc2c8934d7438d7c`;
- six cases, 619.9935 seconds per block. All WAV, PCM, reference, duration, and sample hashes in
  the manifest are frozen; every block must revalidate them before capture.

Saved 15/10 decodes used only by B1:

- Pass A cache SHA-256:
  `166fada340835f1cc3abed7cad9b03944c01edecf329f8a8c1b1320b8e1dd06e`;
- Pass B cache SHA-256:
  `980c622b33c6dd73999ebc174119b55754f34639fbeef831c29539cb4c2ee9f9`;
- each cache has 117 entries: the six-case 10/10 grid plus every complete 15/10 window;
- saved batch lexical results SHA-256:
  `f11ddad31088a8d06456d4202a9b71af3f58b646bc3dc1dc231ce5e26fa1c2b3`.

The saved shadow's `.1084025` macro WER is not a promotion denominator.

## Frozen candidate

- Exact geometry: 15-second window (`240000` samples), 10-second stride (`160000` samples).
- Decode starts: `0,10,20,...` seconds. Only complete 15-second windows are admitted.
- Expected windows per block: Javier `4`, Bill `5`, Keyu `5`, Adam `17`, Jamie `17`, RTFL `8`;
  total `56`. A sub-15-second tail remains provisional until terminal finalization.
- Lexical policy: align normalized lowercase alphanumeric tokens from the already-published
  overlap tail against the fresh window head using the saved semi-global edit-distance rule;
  the aligned prefix is read-only context and is never republished.
- The first proposal owns `[0,15)`. Later proposals start at the accepted publication frontier
  and end at the decode-window end, normally adding ten seconds while `[decode_start,frontier)`
  remains read-only context.
- Speaker policy: decoder-local speaker labels do not become meeting identities. The existing
  session speaker projection labels accepted rolling segments from the settled base surface.
- Goal-1 overlap normalization runs after lexical reconciliation and before the unchanged
  `LiveSession.apply_text_revision` authority seam.
- One rolling witness may be queued/running per session. No runtime feature flag, geometry
  registry, compatibility path, or production default switch is allowed.

B1 must stop if an unmatched word/segment straddles the accepted frontier and no already-measured
rule preserves content without inventing a timestamp boundary or rewriting prior authority.

## Fresh ABBA execution

Exactly 24 actual-live sessions, four blocks and 2,479.974 observed audio-seconds:

1. `10/10-A`: forward case order — Javier, Bill, Keyu, Adam, Jamie, RTFL.
2. `15/10-A`: forward case order.
3. `15/10-B`: reverse case order — RTFL, Jamie, Adam, Keyu, Bill, Javier.
4. `10/10-B`: reverse case order.

Restart whenever the source tree changes. Before every block, require vLLM running/waiting `0/0`
and discard exactly one decoder warm-up. Persist source tree, patch, file hashes, service
PID/start/argv/cwd, descriptor, model, queues, and corpus hashes for every restart/block.

Expected rolling work per arm across two blocks:

- control: `122` model calls, `1,220` decoded rolling-audio seconds;
- candidate: `112` model calls, `1,680` decoded rolling-audio seconds.

## Frozen metric populations

- Quality uses immediate pre-Stop, settled pre-Stop, and post-Stop surfaces. Primary promotion
  accuracy is settled pre-Stop.
- Changed-region correction p95 pools every changed rolling-owned region across all 12
  observations per arm; nearest-rank p95. Also report per-case, category, and legacy-trio
  distributions.
- First-publication p95 pools every non-empty provisional span across all 12 observations per
  arm; nearest-rank p95. Also report per-case, category, and legacy-trio distributions.
- Drain wait and Stop-to-final remain separate clocks. Browser paint and historical shadow word
  availability are not substituted.
- Report both passes and pass-matched comparisons; never require transcript byte identity.

## P1-P6 gates

- **P1 accuracy:** candidate settled macro WER improves by at least `.010000`; every category
  mean WER and DER is non-worse; no case worsens by more than `.02` absolute WER or DER; macro
  matched-word speaker accuracy is no worse by more than `.02`. Report content recall and
  reference-speech DER.
- **P2 latency:** candidate correction p95 `<=15.0 s`; candidate first-publication p95 is no
  more than fresh control p95 + `.500000 s`. Report the historical first-publication gate
  separately.
- **P3 integrity:** exact samples; every eligible window completes; zero text/proposal refusals,
  evictions, failed/stale windows, admission refusals, terminal failures, or dropped commits.
- **P4 resources:** every session and each arm's aggregate combined pre-Stop RTF `<1`; queue max
  one; endpoint quiet before/after; exact decoded-audio and model-call cost reported.
- **P5 stability:** both A and B pass-matched WER comparisons improve directionally and each
  independently passes P2-P4. P1 materiality applies only to the fixed two-pass aggregate.
- **P6 scope:** file mode, terminal finalization, identity policy, 2.5-second provisional cap,
  model, prompt, decoding, and corpus remain unchanged.

Any source/model/corpus drift, queue contention above one, sample mismatch, refusal, eviction,
failed/stale window, dropped commit, or terminal failure aborts the campaign. Retain partial
evidence, fix the cause, and restart the entire 24-session denominator in a new root; do not
replace one observation in place.
