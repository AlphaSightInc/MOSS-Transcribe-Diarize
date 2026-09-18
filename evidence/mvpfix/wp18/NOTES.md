# WP18 measured result

**Identity repair blocked by falsified wiring-only design; independent truncation notice fixed.**
Base d769b010; branch mvpfix/wp18-file-identity. All work confined to this worktree.

F1 — Local file and repo-recorded production startup share the same constructor, which
explicitly disables embedding Tier B and supplies no encoder. The manifest's live matcher
uses score .35, margin .10, matching .5 s, birth 1 s, admission 2 s; file Tier B uses its
own unchanged .70 similarity/.20 margin/2 s segment floor/3-segment selection. File does
not use the live evidence provider or NoLiveSpeakerEvidence. Pinned ONNX path is
~/.local/share/moss-transcribe-diarize/live/voxceleb_resnet152_LM.onnx. Configuration
inventory is source-backed; currently running deployment was not inspected.

F2 — Six minutes, alternating public Bill Ackman/Keyu Jin clips, three voices, three
windows (0–150,120–270,240–360), exactly three serial vLLM requests through own 18118.
Disabled resolver: 7 identities. Enabled pinned provider: 7. Resolver/stitch agree in
both arms. No merged short tail. Identical decoded inputs reused; this isolates the
identity operation from decoder nondeterminism. Same-voice score .994946–1; margin
-.005054–.005054. Perfect fake embeddings: one voice yields 3, two yield 6; every
same-voice score 1, margin 0. This is a reachable arithmetic defect, not evidence that
the thresholds should be tuned. `_tier_b_evidence` also excludes overlap-linked voices.

F3 — COMMON's falsification stop applies. Identity production untouched; cannot claim
31→3 or even 7→3. No identity regression tests claiming success were introduced.
The brief's conditional 30-minute rerun does not apply because production is disabled
also. Needed follow-on is an authorized file identity algorithm/composition design,
measured with the same falsifiers (not a lower margin). Existing live album is a
candidate, not proven drop-in compatibility. Original 30-minute defect remains.

F4 — Separate requested small fix: FFmpeg successful prefix decoding reports
`filesize and duration do not match (growing file?)` at warning level. Healthy 12 s MP3
had empty stderr; 60%-byte prefix had the warning, both exit 0. Preserve only this
condition as fixed safe notice; don't publish raw stderr. Existing decoder output-cap
metadata also becomes a fixed completion notice. Successful recovered media still saves.
Save/reopen tests use the real FFmpeg path, with a fake speech decoder; real identity
probe above uses the real decoder. Absence of warning is not proof of complete media.

Validation and failed attempts: see test-summary.json and COMMANDS.md. Initial tunnel
attempt refused unknown host due to /dev/null known-host file (no GPU request); corrected
to existing known hosts, read-only. First test draft wrongly indexed absent notice keys
(3 failures); corrected to .get, then 2 expected regression failures and 1 healthy pass.
Product fix then passes focused suite. No policy, QUALITY_BOUNDS, readiness, sentinel,
frame shape, window planner, identity matcher, or lifecycle authority changed.

Deviations: falsified identity design stopped per COMMON rather than implementing a
known-insufficient wiring change. Automated state-printing bench replaces interactive
TUI, as the brief requires measured offline evidence. The retained bench is an explicit
reusable falsifier; PCM/decoder cache are ignored local scratch. Verification docs use
`docs/verify/wp18/` to satisfy the repository layout gate. Full suite scratch plugin only
confines hardcoded test paths and sockets inside this checkout.

Bench correction: initial fake segments began before later windows' owned intervals,
so stitching discarded them (resolver 3/6, stitched 1/2). Moved fake segments to 20–25
and 40–45 seconds in every window: all lie inside ownership, so both resolver AND
stitched counts now show 3/6. Original real-audio measurements were unaffected. This
correction prevents segment clipping from falsely looking like identity reconciliation.
