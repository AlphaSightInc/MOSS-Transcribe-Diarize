# WP16 fresh-context verification result

**FAIL overall: the literal stopped-port gate fails. All product/test/evidence gates PASS.**
Port 17877 belongs to WP17, not this verification. No other worktree or service was modified.

Fresh session, 2026-09-18. Tested branch `mvpfix/wp16-file-url-long` at
`d36f0be3279c5385e1ab917123cdcc3dfddd25cb`; product fix
`76665702adfcab6214191f0d373d68abadbfd144`.
Initial tracked/untracked status clean. Import resolved inside this exact worktree.
Read AGENTS.md, VERIFY.md, evidence NOTES/COMMANDS, prototype NOTES and skill,
COMMON.md and execution-plan sections 1–2. No prior conversation used.

## F1 — Fresh gates

Executed every command in VERIFY.md, in its stated order and environment, without
stopping after a failed gate. Python used the specified shared interpreter with local
PYTHONPATH, no bytecode/cache provider, and the committed path-only scratch plugin.
Frontend used the native config loader. Commands and raw logs are retained under
ignored `.wp16runtime/fresh-*.log`; compact results are in
`evidence/mvpfix/wp16/fresh-summary.json`.

| Gate | Result |
|---|---|
| Branch/SHA/initial clean state; worktree import | PASS |
| Full Python suite | PASS: 1,870 passed, 2 skipped, 37 subtests; 21 warnings; 136.26 s |
| Full frontend suite | PASS: 244 tests / 27 files; 2.52 s |
| Typecheck / production build | PASS / PASS |
| Built assets compared with tested commit | PASS: unchanged |
| Evidence verifier | PASS: 16 cases, 5 typed failures, 5 long cases, 50/50 exports |
| Actual retained downloads versus saved API snapshots | PASS: 50/50 freshly recompared |
| Verification-document layout / whitespace | PASS / PASS |
| Product scope versus 5179368e | PASS |
| No listeners on 17876/17877/17878/18116 | **FAIL: 17877 occupied** |

Python warnings: one Starlette, 17 tarfile, three audioread deprecations.
Frontend emitted three Node warnings about a missing valid localstorage-file path;
tests still passed. No test failures waived.

The exact lsof command returned exit 1 **with a listener row**; exit 1 alone does not
establish stopped ports. Read-only attribution via
`ps -p 9630 -o pid=,ppid=,lstart=,command=` and
`lsof -a -p 9630 -d cwd -Fn` identified PID 9630, parent 86942, started
2026-09-18 01:35:16 local, running `prototypes/streaming-diarization/wp17/stack.py`
from `MOSS-Transcribe-Diarize-wt-wp17-lane-quality-voiceprint`, port 17877,
decoder forward 18117. A diagnostic repeat showed the same listener.
No listeners reported on 17876, 17878 or 18116. WP17 was left untouched.
A future literal all-ports-clear pass requires WP17's owner to release 17877;
this verification does not authorize stopping that service.

## F2 — Retained case table, freshly checked offline

These are measurements from the committed browser campaign, not a new live run.
Acceptance/first status/terminal times are elapsed seconds from the browser probe's
start, including preparation; status polling cadence is 2 s, not paint instrumentation.
RSS is maximum sampled current server-process resident memory, not an absolute peak,
process-tree total, system memory or GPU memory. Three samples per long case.

| 30-minute case | Accept / first status / terminal (s) | RSS max KiB | Saved identities / reference voices / distinct clips | Exports |
|---|---:|---:|---:|---:|
| WAV | 0.392 / 0.408 / 88.694 | 742,944 | 31 / 3 / 2 | 5/5 |
| MP3 | 0.131 / 0.141 / 86.438 | 669,616 | 31 / 3 / 2 | 5/5 |
| AAC/M4A (audio-only MP4 container) | 0.160 / 0.169 / 84.442 | 672,512 | 31 / 3 / 2 | 5/5 |
| Concurrent WAV A | 0.263 / 0.275 / 94.615 | 692,976 | 31 / 3 / 2 | 5/5 |
| Concurrent WAV B | 0.282 / 0.293 / 94.589 | 692,976 | 31 / 3 / 2 | 5/5 |

Video-bearing .mp4 was **not measured**. The retained M4A is mono AAC generated from
WAV; do not relabel it as a video-upload measurement. Each long case saved 1,800 s
and used 15 production windows (150 s maximum, 120 s stride). Concurrent cases
share the observed process RSS and a 30-window interval across two workers.
Across 33 samples, RSS was 666,928–742,944 KiB (651.3–725.5 MiB).
Shared decoder queue maxima: two running, one waiting.

| Other class | Terminal s | Outcome / visible reason |
|---|---:|---|
| Direct loopback HTTPS MP3 | 2.088 | Completed; 37 words; MP3 and 5/5 exports |
| Public Wikimedia audio | 2.094 | Completed; one word; MP3 and 5/5 exports |
| YouTube talk | 12.122 | Completed; 479 words; MP3 and 5/5 exports |
| Empty WAV | 2.155 | transcode_failed: “Media could not be decoded. The format may be unsupported or damaged.” |
| Text renamed .mp3 | 2.099 | Same transcode_failed reason |
| Real URL 404 | 0.085 | acquisition_http_404: “The media was not found (404).” |
| HTML URL | 0.089 | acquisition_failed: “The URL returned a web page instead of direct media.” |
| Accepting but nonresponding URL socket | 30.160 | acquisition_timeout: “URL acquisition timed out.” |
| 10 s digital silence | 2.126 | Completed; zero words/identities; “No speech detected.”; MP3 |
| 2 s speech | 2.098 | Completed; six words; MP3 and 5/5 exports |
| MP3 retained at 60% of original bytes | 2.095 | Completed 7.167 s of 12 s; 24 words; no truncation notice; 5/5 exports |
| Actual 177,182,781,440-byte sparse browser File | 0.061 | HTTP 507: “Not accepted: Insufficient storage for upload.”; only admission POST; zero meetings |

All five saved failures had reasons visible in History and header; failure logs
contained no source content. Saved state survived reload; foreign authenticated
workspaces returned 404 in 16/16 final cases. The 50 exports are ten nonempty
transcripts × five formats (Markdown/text/JSON/SRT/VTT); silence and failed meetings
are not counted as transcript-export passes. Eleven completed meetings had MP3s.

## F3 — Prototype verdict and fix 76665702

Question: can real file/URL bytes produce truthful saved outcomes, at scale?
Original behavior was falsified: exact digital zeros produced 32 fabricated words,
one speaker and no notice, despite matching exports. The existing exact-zero
predicate distinguished all five WAV probes, including one-bit and last-sample
signals. File dispatch now checks normalized PCM and bypasses decoding only for
nonempty exact-zero audio; any signal still reaches the unchanged decoder.
Silence now saves zero words/identities plus its notice and MP3 with zero decoder calls.

The browser could spend over 60 s preparing a huge multipart body before reaching
the already-correct capacity refusal. A header-only control returned 507 with zero
body bytes. The prototype accepted 64,078 bytes in 3.58 ms and rejected the huge File
in 1.76 ms. Production now POSTs File.size to `/api/meetings/file/admission` before
sending upload bytes, using the existing free-space rule:
`2 * Content-Length + 512 MiB`. Actual admission checks capacity and multipart
overhead again; preflight reserves nothing, creates no meeting and bypasses nothing.
No fixed upload ceiling was added; URL acquisition retains its separate 2 GiB bound.

Product diff: `phase2_file.py`, `phase2.py`, frontend `fileUpload.ts`, associated
tests and generated assets; remaining changes are scoped evidence/bench/docs and
scratch ignore. Shared decoder, windowing, identity policy, thresholds,
QUALITY_BOUNDS, readiness, nine frame keys, lifecycle checks and sentinel unchanged.
Existing MP3 assertions are unchanged; their synthetic PCM fixture now has signal.
Historical deliberate always-silent mutation failed both intended tests (2/2).
Initial test-author errors and the unexplained transient transcode failure are
retained in test-summary.json; none are counted as product passes.

## F4 — Limits, usage and deviations

All five long cases saved **31 identities for three reference voices** (Bill Ackman,
Keyu Jin, Lex Fridman), from two clips repeated into 30 one-minute blocks.
This demonstrates identity fragmentation, not correct speaker attribution.
Ordered word error denominator is 4,725 reference words per case:

| Case | Substitutions / omissions / additions | Word error rate |
|---|---:|---:|
| WAV | 148 / 46 / 315 | 10.7725% |
| MP3 | 144 / 46 / 301 | 10.3915% |
| M4A | 147 / 49 / 313 | 10.7725% |
| Concurrent A | 148 / 46 / 315 | 10.7725% |
| Concurrent B | 149 / 46 / 315 | 10.7937% |

Repeated content can benefit provider caching. Natural 30-minute diversity,
video-bearing MP4, general speech/identity quality, attended capture, deployment,
current live URL behavior and end-to-end paint latency remain unmeasured here.
Truncated MP3 completion does not establish whole-original-recording completeness.

Decoder usage: retained **158/200**, matching 158 window records; fresh **0/100**
additional. No tunnel, measurement stack, decoder request, deployment, push, merge,
rebase, peer message or shared-service change in this session.
No fresh verification command omitted/retried; ps/lsof diagnosis was added after
the stopped-port mismatch. No production edits in fresh verification.

Historical deviations remain disclosed: default Vite once used the external shared
dependency symlink's transient .vite-temp before switching to native loading; an
early read-only batch used dev cwd; neither was repeated here. Browser probes replaced
the prototype TUI as required by WP16; bench absorbed the validated prototypes.
The offline verifier depends on ignored retained downloads/API snapshots in
.wp16runtime as prescribed; committed evidence alone is insufficient in a clean clone.
Only VERIFY-RESULT.md and fresh-summary.json are added by this verification.
