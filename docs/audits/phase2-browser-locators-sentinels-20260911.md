# Browser locator and sentinel audit

Starting revision: fcde2f9f, production/browser-workspaces-20260910. Local only.

**F1 — No nav-induced ambiguity in the existing predicate selectors.** The nav makes
exact text `Meeting history` match twice (anchor and heading), and `Voiceprints`
match twice (anchor and button). No browser predicate selects those strings by
text. Attribute selectors, region roles, button roles and IDs exclude those anchors.
The mounted shipped HTML/bundle confirms two history text matches but one history
region and one Voiceprints button. No nav change is needed.

**F2 — Existing meeting selection is ambiguous.** `_workspace_html` includes fallback
meeting cards inside `#meeting-history-app`. Preact's initial render leaves these
beside its mounted history region. With an existing meeting, the original global
`[data-open-meeting="id"]` matches two buttons. Local Chrome reproduces the literal
strict-mode violation. This is reachable immediately on final-summary selection,
without opening the voice bank. It also makes account_product_regression's
`count() != 1` raise its misleading "absent" message. The retained host message
omits the selector, so this is a reproduced mechanism, not a claim to have inspected
its exact stack trace.

All five call sites now share `_meeting_opener`, scoped to the exact `Meeting history`
region: account observer, transcript export, visual fidelity, final-summary selection,
and sentinel rendered-body readback. No `.first()` fallback. The fallback cards
still exist in the product DOM; this patch fixes predicate targeting, not rendering.

**F3 — Other summary selectors.** Refresh has two matches when the voice bank is
open; scope it to history. Browser AI settings fields and Save now stay inside their
settings region. The pre-existing `.first` settings toggle is replaced by its named
button. Retry/Regenerate are mutually exclusive branches of FinalSummary, so their
union selects one button; Cancel and summary-state selectors are likewise unique.

**F4 — Audio sentinel title was never installed.** The title PUT in cross_owner_matrix
names a live meeting. The two PUTs in sentinel_absence also name live meetings.
`_seed_audio_sentinel` creates separate file meetings and previously assumed their
upload filenames became titles. `Phase2File.accept` uses only the extension to stage
`input.<extension>` and calls `workspace.create_meeting("file")`; `_create_meeting`
inserts a null automatic title. There is no filename-to-title installation.
The owner GET reads the right file meeting; this is neither wrong-place readback nor
an overwritten sentinel. Now, after terminalization, explicitly PUT the audio marker
title, GET the same owner meeting, require exact title equality, then download and
retain the existing audio checks. A successful PUT without durable readback still fails.

## Complete locator review by family

Reviewed every `locator`, `get_by_*`, `wait_for_selector`, and `eval_on_selector_all`
call in phase2_acceptance_browser.py, phase2_acceptance_summary.py,
phase2_acceptance_external.py and phase2_g7_canary.py, plus the reference UI helper
invoked by the fidelity predicate. Repeated call sites are grouped below.

| Selector family | Cardinality / disposition |
| --- | --- |
| auth bootstrap/signed-in; data-boot ready; data-history-boot ready | One mounted root for the selected state; nav adds none |
| data-workspace-section file/live/history; aria-label Meeting history | One each; unchanged |
| all data-workspace-section | Deliberately plural ordered list; no strict action |
| data-open-meeting with explicit ID | Two with fallback; all five callers now scoped to mounted history region |
| data-observer-mode read-only; data-capture-phase viewing | One capture control subtree in the corresponding state |
| Stop and finalize text/count | No nav copy; absent in read-only observer state |
| #transcript-panel, body | Unique IDs/document element |
| title Export transcript; menuitem Markdown (.md)/Plain text (.txt)/JSON (.json) | Single transcript menu, distinct menuitem names; nav has neither title nor menuitem role |
| input[name=file], textarea[name=urls], button Transcribe files and URLs | One upload form; nav anchors cannot match |
| button Refresh | Two when voice bank open; summary now scopes to history |
| region Final summary; data-summary-state wanted | One selected completed meeting's summary |
| region Browser AI settings; form within it | One settings component and zero/one form |
| settings toggle | Explicit named button replaces pre-existing `.first` |
| Provider HTTPS URL, Model, API key (optional), Final-summary prompt, Request timeout (seconds) | Exact labels scoped to settings region |
| Save on this browser | Exact button scoped to settings region |
| Retry summary OR Regenerate summary | Mutually exclusive branches inside one summary region |
| Cancel summary | One active summary's button |
| G7 microphone/system level aria-label prefixes | One meter per lane; anchors add none |
| G7 Enable microphone, Share audio, Start capture, Stop and finalize | Distinct capture buttons; anchors add none |
| G7 ready/active/terminal capture phase | One capture subtree, state-dependent |
| reference helper .main, #transcript-panel | One reference work area; preparation called with is_reference=True |
| reference helper .tr-legend-right bounding box | One declared transcript exemption per compared work area |

The reference helper's standalone `is_reference=False` branch retains a legacy
`[data-open-meeting].first` selection. The acceptance predicate does not call that
branch: it opens the candidate via `_meeting_opener`. No `.first` was introduced.
JavaScript querySelector calls use unique transcript/app IDs; they do not select nav text.

## Validation

`tests/phase2/test_acceptance_locator_sentinels.py` loads actual `_workspace_html`
and the shipped compiled frontend into local Chrome with intercepted fixture APIs
(no deployment connection). It reproduces two global meeting buttons and their
strict-mode error, opens the scoped interactive card, reaches Final summary, and
exercises Refresh with the voice bank open. Separate collector tests verify explicit
title installation and reject a successful response whose subsequent owner GET
still lacks the title. Initial tests: two failures, one pass; after fixes: three pass.

- `.venv/bin/python -m pytest tests -q`: 1,231 passed, 2 skipped, 37 subtests passed.
- `npm --prefix frontend test`: 155 passed.
- Focused browser/sentinel tests rerun after adding the literal strict-mode assertion: 3 passed.

No host operations, frontend changes, QUALITY_BOUNDS, validator, or identity-policy changes.
These tests establish the local defect/fix; they do not claim deployed qualification.
