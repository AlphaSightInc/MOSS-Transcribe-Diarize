# WP16 — real file/URL scale and failures

**Two measured defects fixed:** digital-zero files fabricated speech; oversized browser
uploads could remain in body preparation without reaching the server's typed refusal.
The ingestion fixes preserve decoder/window policy, identity values, QUALITY_BOUNDS,
readiness, nine frame keys, lifecycle checks and the two-Refresh sentinel.

## Structural contract

Question: do source bytes reach a truthful saved outcome, through the real browser,
for long recordings, supported containers, external URLs and actual damaged inputs?
Primitives are source bytes/size, normalized PCM, decode dispatch, owner-bound saved
meeting, and displayed/exported projection. Each crosses a separate failure boundary;
none of successful download, exported equality, or completed status proves speech accuracy.
Invariants: any nonzero PCM still decodes; exact zeros cannot justify invented speech;
invalid/empty media is not silence; no capacity refusal creates a meeting; actual upload
admission remains authoritative after preflight; ownership and exports preserve saved truth.
Unknowns: natural 30-minute acoustic diversity, real long-file identity correctness,
and recovery of missing bytes from a truncated source. Repetition is a scale probe.
Falsifiers: nonzero suppression, speech on zero input, missing typed reasons, leaked
content in failure logs, foreign-owner non-404, mismatching exports, or a preflight that
creates work/bypasses actual admission. Tools measure those specific boundaries.

## F1 — digital silence

Before: real 10 s mono PCM16 zero WAV -> 32 words, one speaker, no notice; 5/5 exports
matched the fabricated transcript. This falsifies ingestion correctness, even though
export consistency passed. After: zero words/speakers, `completed`, `No speech detected.`
in both History and header, MP3 present, zero decoder calls.

Correction reuses `live_silence.is_digital_silence` at **File dispatch**, after the actual
normalized mix. It does not guard the shared decoder seam or change live behavior.
Five prototype WAVs distinguished exact zero from speech, one-bit quiet signal and a
last-sample signal. Tests include a nonzero sample after a full read chunk.
Six existing MP3 publication/lifecycle assertions expected synthetic speech from zero
PCM. Their common fixture now carries one-bit PCM; assertions are unchanged. A restored
violating control (`_is_silent_mix = lambda _: True`, process-local only) makes both the
quiet-signal regression and original MP3 transcript assertion fail (2/2). No waived tests.

## F2 — scale, quality and identity

Final long durations: WAV 88.694 s, MP3 86.438 s, M4A 84.442 s; concurrent
WAVs 94.615/94.589 s. **50/50 exports match; 158/200 total decoder calls.**
33 current-RSS samples span 666,928–742,944 KiB (651.3–725.5 MiB). Shared
queue maximum 1 waiting / 2 running: contention was observed, not an idle-only claim.
Timings are browser HTTP acceptance/first polled status and terminal polling (2 s
resolution), not instrumented paint timestamps.

See `summary.json` for final browser timings, RSS sampling and full case outcomes;
`word-scores.json` for exact edit counts. Composite is 30 alternating 60 s public corpus
clips, two distinct clips, **three named reference speakers** (Bill Ackman, Keyu Jin,
Lex Fridman). `composite-reference.jsonl` keeps the public reference; boundaries are in
`composite-boundaries.json`. No audio or private transcripts are committed.

30-minute WAV/MP3/M4A and two simultaneous 30-minute WAV workspaces are measured.
Every long meeting uses 15 production windows (150 s bound, 120 s stride; final 120 s),
with unchanged 16,384 context/12,000 output settings from the supplied stack recipe.
Window records contain timings/tokens only. Each concurrent case's resource observation
interval sees both workers; the summary labels that denominator. Server RSS is sampled
current resident memory, not system memory, total process-tree memory or historical peak.

Saved speaker count is 31 despite only three reference voices. This is an identity
fragmentation finding for the identity workstream; no identity policy changed here.
WER is ordered word error against the 4,725-word composite, not a quality gate or
speaker-attribution score. Repetition and identical adjacent window content can benefit
provider caching; these timings do not qualify arbitrary natural 30-minute recordings.

## F3 — tests

Exact attempts, failed tests and final totals: `test-summary.json`.
Baseline full suite: 1,865 passed, 2 skipped, 37 subtests; frontend 242 passed.
After silence fix: 1,869 passed, 2 skipped, 37 subtests; frontend 242 passed.
Final: **1,870 passed, 2 skipped, 37 subtests; frontend 244 passed in 27 files**.
Typecheck/build passed. Full-suite warnings are the existing Starlette, tarfile, and
audioread deprecations; no new application warnings.
Raw logs stay ignored under `.wp16runtime`, compact counts and failures are committed.
No inherited failures were tolerated: WP10's integrated fixes make the baseline green.

## F4 — browser capacity refusal

There is **no fixed upload byte ceiling**. Existing policy requires free space of
`2 * Content-Length + 512 MiB`. URL downloads separately have a 2 GiB acquisition bound.
On this disk the real above-capacity sparse File is about 177 GB, physical allocation 0.
Before: first browser attempt had no response for 60 s; second retained 20 s observation
showed “Submitting…” and zero meetings. A header-only control returned 507 with zero
body bytes, separating correct server admission from browser body preparation.

Prototype: browser File.size -> tiny request -> the existing capacity guard. Small file
accepted; oversized real File refused in milliseconds. Production now POSTs file size to
`/api/meetings/file/admission` before preparing the upload request. Same capacity rule;
no reservation, new size threshold or bypass. Multipart overhead and changed free space
are checked by the existing actual admission again. Final real browser sparse-file probe:
507, safe refusal text, only the admission POST, **zero meetings** (`oversize.json`).

## F5 — actual failure classes and limitations

- Zero bytes and text renamed .mp3: `transcode_failed`.
- Real 404: `acquisition_http_404`; HTML page: `acquisition_failed` with explicit web-page reason.
- Socket accepting without responding: `acquisition_timeout` at the unchanged 30 s timeout.
- Direct loopback HTTPS MP3, Wikimedia audio, and YouTube talk: actual acquisition/decoding succeeded.
- 2 s speech: complete with six words and MP3.
- MP3 cut to 60% of its bytes: **decodable prefix completes**, 7.167 s saved versus 12 s
  in the retained Xing metadata; 24 words, no truncation notice. This does not prove
  whole-original-recording completeness. No absent-byte inference or new truncation policy added.

For each failed meeting, actual History/header reasons and content-free failure logs were
checked. Authenticated foreign workspaces return 404. `surface-recheck.json` corrects two
initial probe mistakes: it targets `.topbar` (not transcript body) and waits for foreign
workspace bootstrap (initial 401s were unauthenticated). Neither was a product defect.
Initial Wikimedia URL had the wrong path and returned a real 404; corrected URL completed.
Original attempts are retained in `events.jsonl`; final per-case files are latest results.

Public sources: https://www.youtube.com/watch?v=UNP03fDSj1U (TED-Ed, Matt Cutts);
https://commons.wikimedia.org/wiki/File:En-us-hello.ogg and its original audio link
https://upload.wikimedia.org/wikipedia/commons/5/52/En-us-hello.ogg .
Own HTTPS certificate trusted only through the measurement process's combined CA bundle;
Playwright ignores that private loopback certificate. No operating-system trust changes.

## Deviations and custody

Real browser/state probes replace a TUI as explicitly required by WP16. Validated probes
are absorbed into the standing measurement bench; prototype verdict remains beside them.
Verification documents use `docs/verify/wp16/` per merged WP13 collision prevention.
Task artifacts/state/caches live in this worktree. **Tooling deviation:** default Vite
config bundling used `frontend/node_modules/.vite-temp` through the mandated shared
dependency symlink (directory mtime observed 01:27 EDT). Generated config files were
transient; no outside source edits or dependency installation. Subsequent/fresh frontend
commands use `--configLoader native` to avoid those outside temp writes. No cleanup
mutation was made outside the worktree.
An early read-only tool batch omitted workdir and read dev files; import check caught this;
subsequent commands explicitly pin WP16. No writes were made by that batch.
Initial test implementation had wrong workspace-helper usage (fixed), and one transcode
attempt failed during concurrent suite execution; immediate standalone replay and subsequent
focused/full suites passed. Cause of that single transcode failure remains unmeasured.

Only this branch is modified. No push, merge, rebase, GitHub, deployment, shared service
changes, or ports 7861/7862. GPU only through own 18116 tunnel; <=2 own in flight and
<=200 total. Request accounting is retained in `requests.jsonl` (line count across restarts),
with matching 158 window records. Own tunnel/server/origin/sampler were stopped;
17876/17877/17878/18116 have no listeners. Fresh verification starts afterward.
