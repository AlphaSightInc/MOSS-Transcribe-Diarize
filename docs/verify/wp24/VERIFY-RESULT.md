# WP24 fresh-context verification — PASS

Fresh session, 2026-09-18. Started on clean `mvpfix/wp24-visual-copy-pack` at
`8d3a285088fd71ab3cd158b2cf23306a596046ff`, in the explicitly assigned worktree.
Python import resolved inside that worktree. Read the committed root VERIFY.md, AUDIT.md,
prototype NOTES.md, WP24 brief and COMMON.md; no prior-session completion was assumed.
The regeneration checks passed. **Owner visual acceptance remains pending.**

## Question and verdict

Question: do the requested UI states render truthfully and legibly at supported widths?
Primitives: source state establishes truth, viewport imposes constraints, DOM/PNG exposes rendering.
Invariants: integrated product assets and existing quality/identity/frame/lifecycle policies unchanged;
real execution, replay, and fixtures explicitly distinguished. Unknowns: physical devices/native picker,
owner pixel judgment and D3 shared-workspace policy. Falsifier: checklist mismatch, missing state,
misleading provenance, measured contrast/name/geometry failure, or an owned listener left running.
Chromium measures presentation; the decoder supplies real public speech; replay covers intermediate states.
The original prototype found five repairable defects and F4/D3 deferrals. This fresh run confirms the
repaired pack's stated checks; it does not prove all possible states correct or close those deferrals.

## Fresh measurements

- **52 states × 3 viewports = 156 PNG/copy pairs**: 1440×900, 1280×800, 400×844.
- Checklist diff against committed `evidence/mvpfix/wp24/pack/index.md`: **zero bytes**.
- Zero horizontal-overflow, unnamed-interactive-control, measured-contrast-failure or checked
  header/panel-overlap occurrences across 156 captures. Both lane badges present in both active states
  at every width; provisional snapshots contain provisional rows. Keyboard focus restoration **3/3**.
- Contrast: **8009 pass / 616 manual-review / 0 fail**, 8625 total occurrences. Original pack: 8019/606/0.
  Dynamic snapshots can differ; pixels, transcript words and timestamps are not equality oracles.
  Gradients/opacity remain manual review. 315 intentional ellipsis candidates; zero other clipping
  candidates, zero positive-tabindex anomalies. These measurements are not complete accessibility certification.
- Visually inspected fresh `browser-active-overlap-1440x900.png` and
  `failure-acquisition_http_403-400x844.png`: lane rows distinct; failure message wraps and remains readable.
  Full-page mobile uses vertical scrolling. Owner must still review all checklist entries.
- Real file upload: **completed, 4 saved segments**. Real browser capture reached two-lane active,
  Stop/finalizing and final through production CaptureClient. Audio devices were fake public-corpus streams.
- Decoder queue before load: **0 running / 0 waiting**. Own tunnel **18124**, stack ports **17884/17885**,
  reference oracle **17886**. **7/100 fresh requests; 56/150 cumulative**; at most 2 in flight enforced by
  the existing local-stack semaphore. All four listeners closed after generation; no provider retry.
- Full Python: **1908 passed, 2 skipped, 37 subtests passed**, 21 warnings, **160.03 s**.
- Full frontend: **250 passed / 28 files**, **2.66 s**. Typecheck and production build passed.
  Built assets byte-identical to the starting commit. No production code changed in this session.

## Findings and source locations

| Code | Finding and disposition | Source |
|---|---|---|
| F1 | Already fixed: selected History secondary text, 4.22:1 → 11.87:1 using existing ink token. | `frontend/src/styles/index.css:3700` |
| F2 | Already fixed: narrow outcome overflow and desktop header collision. | `frontend/src/styles/index.css:3706`, `:3720` |
| F3 | Already fixed: naming applies to “this meeting”, including saved meetings. | `frontend/src/components/TranscriptPane.tsx:345` |
| F4 | Deferred: early Share can fail during microphone preparation, then lose its explanation. Lifecycle behavior outside WP24 copy/aria/CSS scope; retained prior reproduction, not re-induced here. | `frontend/src/components/ControlPanel.tsx:113`, `:135`, `:142`, `:381` |
| F5 | Already fixed: Stop contrast, 4.12:1 → 6.50:1 using existing danger token; fresh sampled Stop ratios 5.48:1 and 6.50:1 both pass. | `frontend/src/styles/index.css:938` |
| F6 | Already fixed: untitled transcript fallback is MOSS. | `frontend/src/components/TranscriptPane.tsx:295` |
| F7 | Newly found/fixed: root verification files violate the repository's merge-safe document layout. Moved both into `docs/verify/wp24/`. Standalone check failed before, passed after. | `scripts/check_verify_layout.sh:6` |
| D3 | Deferred: shared ownership contradicts private/browser-scoped copy. Actual shared-stack screenshots retained; strings unchanged. | Inventory below |

No missing accessible-name/aria defect found in the measured population; no aria repair added.

## D3-dependent strings (unchanged)

- `frontend/src/components/ControlPanel.tsx:343`: “Private to this browser; no sign-in or capture key is needed.”
- `frontend/src/components/VoiceprintBank.tsx:54`: accessible section name “Private voiceprints”.
- `frontend/src/components/VoiceprintBank.tsx:55`: “Private to this browser workspace. Name a speaker during capture to save their voiceprint; no separate recording needed.”
- `moss_transcribe_diarize/app/phase2.py:2323`: “History stays with this browser profile. Clearing site data loses automatic access.”
- `moss_transcribe_diarize/app/phase2.py:2337`: “Private voice bank” heading (visible in mobile layout).
- `frontend/src/components/TranscriptPane.tsx:345`: “When checked, enough clear speech also saves a private voiceprint.”
- `frontend/src/components/TranscriptPane.tsx:188`: “Saved ${result.label}. Voiceprint saved privately in this browser workspace.” Source-inspected success message; shared enrollment was not executed by this regeneration.

The bootstrap-only “History belongs to this browser profile...” at `phase2.py:2290` is separate:
this pack did not show that bootstrap page in shared mode. Browser-local summary API-key wording
at `FinalSummary.tsx:49` describes client storage, not shared transcript/voiceprint ownership.

## Commands and retained evidence

All commands ran from `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp24-visual-copy-pack`.
`PY` below denotes `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/.wp24/tmp" "$PY" prototypes/ui-signoff-pack/run.py --regenerate .wp24/fresh-verification
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" prototypes/ui-signoff-pack/verify.py .wp24/fresh-verification
diff -u evidence/mvpfix/wp24/pack/index.md .wp24/fresh-verification/pack/index.md
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/.wp24/tmp" "$PY" -m pytest -q -p no:cacheprovider tests --basetemp=.wp24/test-fresh-session
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
bash scripts/check_verify_layout.sh
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets
```

Logs: `evidence/mvpfix/wp24/checks/fresh-*`; result, counts, queue, keyboard and aggregate measurements:
`evidence/mvpfix/wp24/fresh-*.json` and `fresh-queue-before.txt`. The empty checklist/build diffs record equality.
The failed pre-move layout check is retained as `checks/fresh-layout-before.txt`. Regeneration and full suites
passed on their first attempt; no failed provider attempt was hidden or retried.

Owner's committed pack: [52-state checklist](../../../evidence/mvpfix/wp24/pack/index.md).
Fresh local regenerated pack: [.wp24/fresh-verification/pack/index.md](../../../.wp24/fresh-verification/pack/index.md).
Fresh PNGs/copy and runtime remain ignored; committed aggregate evidence compares them to the retained pack.

## Boundaries and deviations

This session changed verification documents/evidence and the capture harness's request cap/check only.
The user's stricter 100-call cap overrides the prior generator allowance of 101 remaining calls.
The user's explicit full-suite request overrides the old VERIFY.md's “no need to rerun” guidance.
The requested docs path also repairs F7. Prototype regenerated; no new product algorithm or policy introduced.

Intermediate active/provisional/lease-expiry evidence is replayed from retained genuine production responses;
failure/no-speech/truncation/audio/history states use labeled fixtures, summary states use fake endpoints.
Native picker/physical devices and full end-to-end induction of every state remain unmeasured.
No operator-reserved fidelity gate, push, merge, deployment, shared-service restart or peer dispatch occurred.
No TLS keys, cookies, databases, profiles or audio were committed. F4, D3 and owner sign-off remain open.
