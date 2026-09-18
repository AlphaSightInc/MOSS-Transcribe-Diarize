# WP18 prototype verdict — identity wiring-only fix FALSIFIED

Question: is file cross-window identity active, and can wiring the existing embedding
provider reconcile repeated known voices without changing policy or algorithms?
Primitives: window-local speaker, sampled voice vector, overlap component, canonical label.
Invariants: unchanged text/timing, matching thresholds, live policies, lifecycle and bounds.
Unknown before probe: file/live composition parity and competing-match semantics.
Falsifier: enabling the pinned provider still leaves duplicate known voices.
Tool decision: one 6-minute real decode (3 serial requests), replayed through both resolver
configurations, distinguishes provider omission from matching and stitching defects.
The fake embedder supplies perfect independent vectors to remove acoustic uncertainty.

Measured: disabled/enabled both 7 identities for 3 reference voices; resolver and stitched
counts equal. Pinned CPU provider available. Repeated true-voice similarities 0.994946–1;
margins -0.005054–0.005054, below unchanged 0.20. Perfect fake one-voice/three-window
case yields 3, two-voice case yields 6, both with cosine 1 and margin 0. No wiring fix.
`_tier_b_runner_up` treats another occurrence of the SAME voice as a rival identity.
`_tier_b_evidence` also omits already overlap-linked components from embedding candidates.
The local and production Account constructor explicitly set Tier B disabled; the live
manifest is passed only into the live runtime. No NoLiveSpeakerEvidence is used by file.
The conditional 30-minute rerun does not apply: production construction is also disabled.

COMMON.md requires stopping a falsified fix. No production identity code/policy changes.
Needed follow-on: separately authorize and prototype file identity algorithm composition
(e.g. the existing album), with the one/two-voice three-window failures as acceptance tests.
Do not equate enabling the old pairwise matcher with album unification in ADR-0002.
The probe is retained as the shared bench's reproducible falsifier, not product code.
It prints decisions after each action instead of a TUI: unattended measured evidence is
required by the brief. Real transcripts/audio remain ignored scratch; only safe metadata
and resolver decisions are committed.

Independent small truncation fix question: can a reported media warning survive completion
without retaining raw stderr? Primitives: transcoder fact, fixed notice, saved meeting.
Invariant: successful recoverable audio still transcribes; no raw path/content in notice.
Falsifier: healthy MP3 warned, truncated reported MP3 not warned, or decoder cap lost.
Real 12-second MP3 / 60%-byte prefix: FFmpeg returns 0 for both; only prefix emits
`filesize and duration do not match (growing file?)`. This supports preserving the warning;
not inferring truncation for media whose decoder/transcoder reports no such fact.
