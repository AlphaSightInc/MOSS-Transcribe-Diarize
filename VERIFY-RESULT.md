# WP12 fresh-context verification — PASS within measured scope

Date: 2026-09-18. This user turn began with fresh context and explicitly required
the additional matched instrumentation before full verification. Starting branch
`mvpfix/wp12-stop-latency-identity`, clean at
`a02a8491cbedc66278538031230518dbce672293`. All commands ran in the WP12 worktree;
package import resolved there. Production code remains that exact revision.
Continuation changes only bench instrumentation, evidence, and documentation.
No same-context reread is being presented as another fresh session.

## V1 — full gates

Commands from root VERIFY.md were executed after matched measurement, using the
specified Python and worktree-local test adapter, without installs:

- `bash prototypes/streaming-diarization/wp12-stop-identity/check-python.sh`:
  **1802 passed, 2 skipped, 21 warnings, 37 subtests passed, 144.84 s**.
  Full `tests`, no cacheprovider. Log: `evidence/mvpfix/wp12/fresh-python.txt`.
- `bash prototypes/streaming-diarization/wp12-stop-identity/check-frontend.sh`:
  **26 files / 230 tests passed**, **typecheck passed**, **build passed**.
  Log: `evidence/mvpfix/wp12/fresh-frontend.txt`. Generated assets unchanged.
- `<WP12_PY> prototypes/streaming-diarization/wp12-stop-identity/audit.py`:
  **339/1200 decoder calls, peak 2 in flight, 11/11 final/saved agreements**.
  Historical 24 s exact segment equality and 24/60 s ordered per-speaker word
  equality pass; new matched serial/concurrent **12/12 saved dictionaries equal**.
  Result: `evidence/mvpfix/wp12/fresh-audit.json`.
- `<WP12_PY> prototypes/streaming-diarization/wp12-stop-identity/analyze_embeddings.py`:
  matched phase and audio accounting retained in
  `evidence/mvpfix/wp12/matched-embedding-audit.json`.

No production/test assertions altered. Test-generated WP2 PNGs restored using
VERIFY.md's explicit three-file command. `git diff --check` passes. No listeners
on 18112/17872 after measurement (`lsof` empty, expected exit 1).

## V2 — matched diagnosis

Three real-stack runs, same paced public-corpus 24 s parity input:

| Arm | Stop→terminal | Stop→observed final | Decoder calls |
| --- | ---: | ---: | ---: |
| Mono 37979e53 | 0.383135 s | 1.880702 s | 13 |
| Serial lanes b31683a6 | 2.733792 s | 11.327668 s | 26 |
| Accepted concurrent lanes a02a8491 | 2.326931 s | 6.839325 s | 26 |

Serial pre-terminal delay: remaining rolling work 0.897933 s, queued causal work
1.108433 s, tail 0.722543 s, identity sweep 0.002924 s. Mono: tail 0.369481 s,
sweep 0.001617 s. No fixed timer or lease delay; notifications release the drain.

Serial terminal embeddings: system 1 call / 8 intervals / 21.33 audio-seconds /
3.287698 s; microphone 1 / 4 / 22.20 / 3.416678 s. Combined 43.53 audio-seconds,
6.704376 s. Mono terminal: **zero embedding calls**; its speaker mapping uses
time overlap. Lane albums already supply the retained reference vectors. New
terminal probe intervals differ from causal units: 0/12 exact interval matches,
0/2 whole embedding calls repeated. 40.29 audio-seconds overlap causal audio;
same audio coverage does not make different interval encodings interchangeable.
One 5.28 s interval repeats part of a rolling call, but no individual vector was
retained. Dominant cost belongs to the current acoustic-probe algorithm.

Per user's explicit inherent-cost stop clause, **no new production fix** or
further concurrency work. Identity allegation remains **falsified** by the
two-voice mic fixture (Lex Fridman 25–35 s); no identity change.

## V3 — custody, limits, deviations

New requests: 65. Total: 339. Each batch checked running=0/waiting=0 via owned
tunnel 18112; local service port 17872. All started processes stopped. Archived
baseline source compared directly against git: mono **86/86 Python files equal**,
serial **89/89 equal** (`baseline-source-audit.json`). No push, merge, deployment,
shared-service changes, external messages, or modifications outside this tree.
No audio, transcripts, private databases, or credentials committed.

VERIFY.md's obsolete 300-call/no-provider wording was superseded by this user's
explicit 1200-call measurement instruction and updated accordingly. No production
changes followed the fresh-context start, so full suites verify the existing
accepted implementation independently. Bench instrumentation is retained as an
extension of the standing measurement bench, not an alternate implementation.
Minor failed inspections and corrected prose count are recorded in NOTES.md.

**Not full WP12 latency acceptance:** 24 s concurrent remains above 4 s. Prior
60 s concurrent prototype remains 16.174951 s, above 10 s; no new 60 s run. 180 s,
additional matched alternation arms, 30-minute scaling, and multi-meeting
contention remain unmeasured. Further work stopped under the inherent-cost clause,
not because the increased budget was exhausted. Saved equality is not a claim
of human-adjudicated word/speaker accuracy.
