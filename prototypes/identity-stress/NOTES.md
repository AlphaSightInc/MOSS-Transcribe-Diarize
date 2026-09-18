# WP7 identity stress verdict — 2026-09-17

Question: do identity, voiceprint recognition/abstention, rename and bank operations
hold under supported adversarial inputs? Primitives: timed PCM, stable speaker ID,
quality-gated evidence, private profile, display label. Evidence and ID must remain
separate from text and names. Unchanged floors/match rules and lifecycle are invariants.
Falsifiers: extra voice ID, switched person, unknown false name, lost saved name,
or duplicate bank sample after repeat enrollment. Decoder and real CPU embedder are
necessary because fixtures alone cannot establish acoustic behavior.

Verdict: **MIXED / the universal claim is falsified**. No identity-policy fix justified.
- Single Adam Frank 60 s (corpus 49–109): 1 birth, 1 final used ID, 0 final switches.
- Same clip with digital silence replacing 25–35 s: 2 births, 1 final used ID,
  0 final switches. Extra birth in span 25.25–27.75, wholly inside zero PCM.
  This is a reachable silent-span admission finding for WP3, not evidence that the
  final transcript splits one speaking person. Do not prune historical ID registry
  or change manifest thresholds to hide it. Album and snapshot evidence retained.
- Bill 0–29 + Keyu 0–25 + Bill 0–6: 60 s, 2 births, 2 final IDs; 0 switches/person.
  One switch-straddling final segment is excluded from identity switch scoring.
- First two full-reference inputs (154 words): saved output ending <=54 s has
  Bill WER 10/106, Keyu 6/48. Two exclusive Bill words are assigned to Keyu's ID
  at 29.02–30.05, with 2 duplicate words. Exact switch is 29.00: segment does not
  straddle it, so oracle remains failing. Both voices here entered the SYSTEM lane;
  this corroborates mixer/decoder-boundary behavior, not WP4's failed dual-lane rerun.
  No word timestamps exist for the repeated 6 s; no guessed partial reference used.
- Same voice simultaneously on two lanes: 1 birth/final ID, expected current-base
  failure of future two-namespace contract. WP1 owns that change.
- Enroll -> next meeting: correct API label at 3.520 s, under existing 4 s reference
  bound; browser-visible first-name latency remains UNMEASURED. Unknown Keyu: no name.
- Delete -> same voice: no old name. Replacement enrollment creates a new profile.
  Re-enroll another meeting: same replacement ID, sample count 1 -> 2; immediate
  repeat stays 2, label changes persist. Earlier 6/8 s attempts were still pending;
  the 12 s follow-up waits for eligible album evidence and succeeds. No threshold change.
- A 3 s recording initially stopped before first decode: no naming action occurred.
  Follow-up waited while active: naming HTTP 200/pending, bank stays empty at Stop.
  Only provisional evidence existed. This is correct: 2 s eligible album speech is
  required, not 2 s recording length. UI explicitly allows pending enrollment.
- Fresh CPU embeddings: 2/2 known correct, 2/2 unknown abstain. Eligibility probes:
  1.99 s rejected, 2 s/3 s accepted. Existing five-speaker 470-probe result not rerun.
- Post-Stop/reload name mutations return 404, per active-only contract; unchanged.
  Browser History selection/reload preserves name. All 5 real downloads match names,
  words and timing. History cards themselves have no speaker-name field; documented
  separately from the selected historical transcript, which does show the name.

Measurements: 13/13 identity meetings completed/final. 149/150 decoder requests
(130 initial + 19 follow-up), <=2 simultaneous requests enforced. Part 0 used another
20/20 and was interrupted; no retry. See evidence/mvpfix/wp7/{summary,stress-results}.json.
Album dispositions are observations, not unique people; full chronology in
album-events.jsonl. Unpublished abstentions cannot be counted from snapshots: UNKNOWN.

Part 2: fixes confined to proven Part-0 instrument defects, committed separately.
No identity/session/UI/voiceprint production change: supported naming and bank behavior
is correct; outstanding silence/lane producers belong to WP3/WP1. Lifecycle unchanged.

Commands (cwd this worktree; use COMMON.md Python, PYTHONPATH=., PYTHONDONTWRITEBYTECODE=1):
- stack: python prototypes/identity-stress/stack.py --state .wp7runtime/stress
  --cert .wp7runtime/cert.pem --key .wp7runtime/key.pem --port 17867
  --vllm-base-url http://127.0.0.1:18107/v1 --max-requests 150
- replay: python prototypes/identity-stress/run.py all
- CPU: python prototypes/identity-stress/cpu_probe.py
- read-counts: python prototypes/identity-stress/summarize.py (needs ignored raw scratch)
The one-command replay retains the measurement bench instead of shipping a TUI.
Set TMPDIR=$PWD/.wp7runtime/tmp for every process. Never rerun this budget implicitly.

Deviations/failed attempts: batch state traces instead of interactive TUI; first
observer import used incorrect class name, corrected before any request. Initial
local stacks inherited system TMPDIR, so provider temporary WAVs used/removed system
temp before that was corrected for follow-ups. All retained files and edits stayed
in WP7. Original Part-0 54 s replay cannot finish within its 20-request cap. No claim
of full acceptance, attended capture, browser latency, or fresh-context verification
until VERIFY-RESULT.md is written by the /new session.
