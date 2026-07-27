# PRD - MOSS live meeting transcription MVP

## Goal

> Make a real meeting transcribable end to end: the MacBook `m4mbp` captures system audio and
> microphone as two independent lanes, streams them over pinned HTTPS across LAN or Tailscale to
> `ga0-alienware-rtx4070ti`, which transcribes and diarizes on CUDA, and a server-hosted `/live`
> page shows the transcript with speaker labels continuously — for meetings longer than 15
> minutes, surviving a 5-second network interruption without silently losing accepted audio.
>
> The authoritative plan, with measured evidence and the committed design decisions D1-D13, is
> `/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/docs/live-capture-gap-and-execution-plan-20260727.md`
> (revision 3). Read it before the first change of any work item. This PRD is the acceptance
> contract; that document is the design rationale.

## Acceptance bar

The loop is complete only when every point below holds, with evidence (commands run, artifacts
inspected, before/after deltas) recorded in progress.txt:

- **W1 keeper merged to `main`:** the *built* `MOSSCaptureApp` and *built* `mtd-capture` complete
  the real two-step pairing (`/api/live/pairing-codes` → `/api/live/pairings` →
  `/api/live/sessions`) against a real TLS server over real same-user UDS, with full-certificate
  pinning; the **app** (never the CLI) reads view authority and writes the pasteboard; microphone
  and system-audio permissions have explicit per-lane request → pending → granted-or-denied
  transitions; a denied lane emits a typed lane failure rather than staying absent; frames are
  retained until acknowledged; lanes are converted to 16 kHz mono on the Mac. Verified by: Swift
  suite green, full Python suite green, the darwin real-process tracer passing with zero skips,
  and the new-scope discriminator red before / green after.
- **W2 keeper merged to `main`:** view authority is bound to the session lifecycle (active +
  2 h finalization grace + 12 h absolute cap + immediate revoke) and a 900-second fixed expiry is
  unreachable; a failed or ambiguous frame send cannot silently lose accepted audio. Verified by
  deterministic tests covering virtual 60-minute duration, cap boundary, grace boundary,
  revoke-on-abort, 5-second outage, ambiguous-success retry, duplicate retry, 429, and outbox
  overflow surfacing a typed degraded state.
- **One exact SHA everywhere:** `git rev-parse HEAD` is identical for local `main`,
  `origin/main`, the server checkout at `/mnt/d/Coding/MOSS-Transcribe-Diarize`, and the m4mbp
  checkout; the value is recorded in progress.txt.
- **Live service answering:** from m4mbp, `https://100.64.0.8:7861/live` returns 200 and
  `https://100.64.0.8:7861/api/live/descriptor` returns 200 over pinned HTTPS.
- **Batch service unharmed:** `http://192.168.68.38:7860/` still returns 200 over plaintext and
  its job routes still work.
- **Signed app installed:** `/Applications/MOSSCapture.app` exists; `codesign -dv` reports
  identifier `com.alphasight.moss.capture`; the designated requirement names the project signing
  certificate leaf and is unchanged across a rebuild.
- **Permissions granted:** Microphone and System Audio Recording are granted on m4mbp and
  `mtd-capture status` reports both lanes active.
- **60-second canary passes:** two speakers plus identifiable system audio produce a
  continuously updating transcript with speaker labels in the browser; committed p95 ≤ 4 s;
  decoder p95 RTF < 1; both lanes accepted and accounted with zero loss and zero double count.
- **300-second locked certification passes:** simultaneous lanes, silence/mute, a 5-second
  network interruption, ambiguous retry, duplicate retry, two speakers, clean stop/drain — plus a
  separate mic-granted / system-audio-denied run that still produces transcript. Committed
  p95 ≤ 6 s; decoder p95 RTF < 1; zero accepted-audio loss; viewer still authorized past 15
  minutes and through the grace window; outbox and memory bounded.
- **Secret hygiene proven:** no bearer token, device token, view token, or pairing payload
  appears in any CLI output, log, URL, telemetry file, or browser storage; no raw audio is
  persisted.
- **Rollback rehearsed and recorded:** live service disabled, server checkout reverted to
  `163e969`, and `http://192.168.68.38:7860/` still serving — then restored.

## Constraints

Non-negotiable, in addition to the rules in prompt.md:

- **Domain-contract values.** These are part of the domain contract, not incidental constants,
  and must be implemented exactly rather than "generalized away": canonical live sample rate
  16000 Hz; lanes exactly `system` and `microphone`; live frame size 8000 samples (0.5 s); pump
  interval 0.5 s; `hard_cap_samples` 40000 (2.5 s); `min_silence_samples` 8000 (0.5 s);
  `max_retained_samples` 960000 (60 s); client outbox 15 s per lane; helper lease 30 s; view
  grace 2 h; view absolute cap 12 h; batch port 7860 plaintext; live port 7861 TLS; bundle id
  `com.alphasight.moss.capture`; app path `/Applications/MOSSCapture.app`.
- **One writer.** This loop is the only autonomous writer on this repo. The governed
  `aisight-coding-loop` control plane must stay halted — its `.stop-after-current-role` sentinel
  must not be removed. Never invoke `scripts/promote-keeper.sh`, `scripts/revert-feature.sh`, or
  anything under the control plane's `scripts/`.
- **Do not touch `scripts/aisight-coding-loop/`.** It is an inert older loop bundle whose files
  have the same names as this one. Read and write only `scripts/ralph-afk/`.
- **The certificate pin deliberately bypasses PKI.** `PinnedCertificateURLSessionDelegate`
  compares the leaf SHA-256 and does not call `SecTrustEvaluate`. That is correct for an
  exact-leaf pin on a private tailnet. Do not add chain or hostname evaluation.
- **Never weaken security posture to make a step pass:** no disabling SIP or Gatekeeper, no
  global trust changes, no plaintext live transport, no widening the private-network peer
  allowlist, no public-internet exposure.
- **TCC cannot be scripted.** Microphone and System Audio Recording grants require physical GUI
  clicks on m4mbp. When the loop reaches that point it must record the exact click sequence in
  progress.txt as a blocker and move to another candidate — never retry, never attempt to write
  the TCC database.
- **Deploy only a reviewed SHA.** Push and deploy only after the relevant work item's gate is
  green. Never deploy from a feature branch, never force-push.
- **Reversibility.** Every server or Mac mutation must have its rollback command recorded in
  progress.txt before it is applied.
- **Out of scope** (see plan D12): the RTX 4090, durable transcript persistence and export,
  speaker rename/merge, search, browser-initiated capture start, linking `/live` from the batch
  UI, a Windows client, Developer ID or notarization, provisional/partial decode, and
  intermittent-speaker identity calibration.

## Budget and stop

- The launcher argument sets the iteration budget; one logical change per iteration.
- Stop early only via the completion contract: acceptance bar met with evidence, or every
  remaining item blocked on input the loop cannot obtain (in practice: the TCC clicks), recorded
  in progress.txt.
- A blocker ends the iteration, not the loop: record it, commit anything useful, and let the next
  iteration attack it or route around it.
