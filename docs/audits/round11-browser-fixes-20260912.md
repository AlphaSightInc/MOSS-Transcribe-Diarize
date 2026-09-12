# Round 11 browser and relay repairs

Three acceptance/probe defects repaired; no transcription, identity, polling or relay product behavior changed. Source starts at `1dee922d`; retained host round is `c70a96e2`. Host evidence was read locally from `/tmp/moss-round11-stage/result/` (MacStudio-local (not in repo)); no host operations or operator 17861 database access.

## F1 — the page never became hidden

Both layers retain stage `background.enter-hidden`, function `document.visibilityState === 'hidden'`, signed-in/ready boot state. Thus the run never began the post-hidden counter and does not establish a product polling failure. Local headless Chrome reproduces `visible` after another tab is foregrounded; disabling focus emulation through a separate CDP session also leaves it visible.

The existing 45-second background bench already solved the tooling issue: Playwright's own driver session enables always-focused emulation; its launch switches also disable normal background throttling. Reused that measured primitive as `phase2_browser_visibility.unfocused_driver`, with the old prototype importing it. It copies the driver to a temporary directory, changes only its focus override, and refuses a changed/unrecognized driver shape; shared Playwright files remain untouched. The product predicate now uses it and omits the three background-disable switches. Native visibility, original 30-second visibility wait, 2.5-second observation, and counter that accepts only requests issued after hidden entry remain intact. No JavaScript visibility override, frozen page or synthetic visibility event.

Measured on the actual isolated workspace: **hidden for 2.505 s, 6 post-hidden completed requests, read-only observer retained**, Chrome `153.0.8010.37`. Fresh own session on 17863, no audio/decoder inference needed, explicitly aborted after measurement. The synthetic-browser regression also checks actual hidden state and continuing requests. This establishes the repaired measurement on local headless Chrome, not a new host gate pass. [Workspace evidence](../../evidence/round11-browser-fixes-20260912/workspace-hidden.json).

## F2 — G9 omitted owner registration

`measure_browser_summary` directly POSTed the second owner's live session, then `_seed_live_transcript` indexed `campaign._live_helpers[meeting_id]`. Direct creation never registered that entry, causing the retained KeyError before any seeded speech. Use `campaign._new_live_id("b")`, the same owner-registration path repaired for G8 in `15b35860`. Existing Stop/abort cleanup stays unchanged. The regression enters the real G9 preparation function and asserts owner-b registration → seeded owner-b session → Stop; bypassing registration raises the original missing-entry error. Existing real helper/replay lifecycle tests remain green.

## F3 — old summary satisfied the relay completion wait

Host stdout/stderr reports all **8 external checks true**, but **0 relay upstream requests and all 6 relay checks false**. This is not the old external-form selector timeout; browser startup, external HTTPS/CORS and persistence had already succeeded. Retained output does not include the previous DOM attempt ID, so the exact host event ordering cannot be reconstructed from it.

The probe sampled `data-summary-attempt` immediately after reopening a meeting, before its previous summary necessarily loaded. If that sample is null, the old persisted current artifact arriving later passes `attempt !== previous`, letting the probe inspect relay calls before the new request finishes. A real-browser regression reproduces this ordering: the old predicate succeeds while the corrected new-attempt wait is still pending. It requires no OS, TLS, port or working-directory condition; faster/slower scheduling exposes the bad synchronization assumption.

The repair captures the actual POST `/api/meetings/{id}/summary` response, requires HTTP 200, and waits for **current state with exactly that new attempt_id**. It preserves every external/relay assertion and existing deadlines; no sleeps or retries mask the race. The full deterministic probe returns **0**, external **8/8**, relay **6/6**, exactly **1 upstream request**, with relay models configured in its isolated app. [Result](../../evidence/round11-browser-fixes-20260912/probe.json), [retained host failure — removed; inventory](content-boundary-files-20260912.json).

## Validation boundary

Focused browser visibility, stale-artifact, provider-path, helper-lifetime, timeout-evidence and completion checks: **35 passed**. All new browser tests use the shared missing-executable guard; required-file behavior is unchanged. [Focused output — removed; inventory](content-boundary-files-20260912.json). Host qualification must be rerun on the patched candidate; this audit does not declare the failed host rows passed retrospectively.

Full regression: `.venv/bin/python -m pytest tests/ -q` — **1538 passed, 2 skipped, 37 subtests passed**, 110.53 s; [output — removed; inventory](content-boundary-files-20260912.json). No frontend source changed. The owned local stack was stopped after verification.

Integration rebase onto `5993afcb` includes peers' reference-bootstrap, partial-audio seeding and terminal-tail changes. Post-rebase focused checks spanning those changed areas plus these fixes: **301 passed** in 35.55 s; [output — removed; inventory](content-boundary-files-20260912.json). The 1538-pass full-suite count above belongs to the pre-rebase tree.
