---
id: T-32
map: map-002-phase2-multiuser
title: Post-Wave-1 sequencing — private voice bank or client-configured LLM next
type: grilling
status: closed
assignee: codex-20260827
blocked_by: [T-25, T-26]
---

## Question

After Wave 1 ships Accounts, isolation, Live/File Meetings, Account history, and live MP3,
which remaining family ships next: the private voice bank or client-configured language-model
assistance?

Decide with the operator once *Client-configured LLM — functions, browser ownership, artifact
access, and UI contract* is closed. Compare the two already decision-complete families by their
user value, dependency on Wave-1 seams, schema/UI collision risk, and acceptance cost. Record one
Wave-2 choice and leave the other as Wave 3; do not combine them merely to avoid choosing.

## Resolution

**Accepted — private voice bank ships in Wave 2; client-configured LLM ships in Wave 3.**

- **D1 — Wave 2:** After the usable Accounts/isolation/Meeting/audio cutover, implement the
  closed private Voiceprint-bank design. It reuses Wave 1's Account workspace, SQLite ownership,
  Meeting Speakers, transcript speaker editor, and authenticated snapshot polling. Its live
  matching, enrollment, rename, deletion, and versioning behavior remains exactly as settled;
  this sequencing decision does not reopen thresholds or privacy policy.
- **D2 — Wave 3:** Implement the closed client-configured Final-summary design only after the
  private voice bank ships. It remains an independent browser-owned, post-finalization module;
  it does not become part of Voiceprint storage or matching. Future Final summaries may consume
  the finalized transcript labels produced by Wave 2 without changing transcript truth.
- **D3 — Separation and acceptance:** Do not combine the families into one release. Wave 2 owns
  the Voiceprint tables, Account Speaker Identity module, transcript rename behavior, and Bank
  screen. Wave 3 separately owns Summary artifacts, browser-local endpoint settings, and the
  Transcript | Summary surface. *Phase-2 acceptance gates* retains ownership of the exact
  reproducible bars for each wave and their Wave-1 regression checks.

This ordering adds no domain term and changes neither family's closed design or evidence limits.
