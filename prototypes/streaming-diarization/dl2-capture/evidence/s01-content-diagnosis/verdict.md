# S01 content diagnosis — diagnostic only

## 1. Raw retention

Local and remote raw are intact and byte-equal. Nothing was deleted. The operator-directed TTL
deadline remains 2026-08-06 23:05 EDT.

## 2. Batch ASR

The batch service is healthy. Pinned control `1m-acquired-jamie-dimon` (audio SHA-256
`441a8177…`) completed as job `77bc16ec2ae6` with 521 generated tokens and 17 parsed segments.
Exact-repeat S01 jobs `cbf557969083` (microphone) and `85b2a792dc6c` (mixed) both produced 59
tokens and zero parsed segments. Direct inspection recovered the microphone model text:

`[101.98][S01][102.98][104.78][S01][105.78][106.24][S01][107.24]`

It contains timestamps and speaker markers but no words. The batch runner correctly refuses it at
`vllm_runner.py:277-278`. This is an S01 audio-content result, not batch-service drift.

## 3. System lane — root cause proven

**Root cause: Safari source playback paused; the capture tap did not fail.** Safari records 27
`isPlaying=true` updates, then an explicit `HTMLMediaElement::pause` and Playing→Paused transition
at 14:01:59.044 EDT. It records zero Playing updates afterward through capture stop. The retained
system track becomes silent at 14:02:00.612 EDT, 1.568 seconds later—one capture/buffering interval.

H1 stale binding is refuted: production creates a global `CATapDescription` and a tap-only private
aggregate, with no physical output UID (`SystemAudioTap.swift:112-150,261-275`). Current and S01
default output is device 112, UID `BuiltInSpeakerDevice`, MacBook Pro Speakers, 48 kHz. S01 itself
captured loud Safari audio before Safari paused.

H2 format zeroing is refuted: the production path started 1-channel 48 kHz Float32 → 1-channel
16 kHz Float32 conversion and carried valid audio through it. No format/rate/route change, overload,
tap failure, or premature tap stop occurred; the aggregate stopped cleanly only at session end.

H3 process scope is refuted: the production descriptor is global rather than process-listed, and
S01 captured Safari while it was Playing. F4b on the same deployed SHA and machine captured many
new `say` processes plus a second system phase after a 25-second quiet interval. F4b and S01 used
the installed signed GUI app; no launch-context difference explains S01.

The `swiftpm-testing-helper` warnings at 14:09 are test-generated after S01 and are not app evidence.

## 4. Microphone lane

Current default input is MacBook Pro Microphone. The selected S01 interval is nonzero but nearly
steady low-level signal (~−41 dB mean); mixed follows microphone at ~6 dB attenuation once system
audio becomes silent. The project ASR detects only empty timestamp events. Evidence supports
wrong/distant input or speech not reaching the default microphone, not a parser regression.

Minimal action: no app relaunch, re-pair, TCC, device, format, or service change. For the next
system-bearing phase, the operator presses **Play** in Safari and confirms the player remains
Playing; use interview speech, not music. This diagnosis does not itself authorize another session.
