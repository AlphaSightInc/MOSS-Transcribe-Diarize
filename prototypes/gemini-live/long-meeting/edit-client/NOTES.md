# P75 edit client — contract and product-path measurement

Question: can one durable passage text edit coexist with assignment of a section and rename of a displayed name?
Primitives: durable passage id (text write); clicked section passage ids (assignment scope); unsaved draft; one pending save; matching speaker display names (rename membership).
Invariants: Save/shortcut/outside click write once; Cancel/Esc write nothing; failed save retains draft; text never changes speaker/time/audio; assignment touches selected ids only; rename touches every matching id only; voiceprint only clicked id.
Unknowns: real Chrome durability pending server integration; actual provider/refinement behavior unmeasured and out of this $0 run.
Falsifier: duplicate PUT, lost draft, wrong assignment/rename scope, missing Edited metadata after History, export retaining old text.
Tool decision: existing DOM tests exercise production rendering and fake route seams; real Chrome exercises native focus and capture plus production persistence. Full suites catch regressions. No new threshold or algorithm: interaction policy fixed by P75-EDIT-CONTRACT.

One command (repo root): cd frontend && /opt/homebrew/bin/npm test -- src/components/textEdit.test.tsx src/components/speakerRename.test.tsx src/components/TranscriptPane.test.tsx

Prototype: contract regression tests on production base f9d13595. Red logs in ~/Documents/Codex/2026-09-28/moss-gemini/evidence/P75/edit-client/.
DOM verdict: contract implemented. Final six-file baseline 53 failures / 90 passes; product all 143 pass inside full 599-test frontend gate. Typecheck/build green. Browser regressions 26/26 pass. Server DONE observed and merged locally at ea6ce764. Real Chrome durable workflow GREEN; integrated full backend GREEN: 2943 passed, 9 skipped, 2 xfailed, 37 subtests; 419.05s, exit 0. Candidate product: frontend edits, helpers, metadata propagation and tests. This NOTES is throwaway measurement documentation, no product runtime.

Reachable failure measured and fixed: native keyboard blur did not bubble to parent onBlur; onBlurCapture observes the actual event. Edited repeated words must bypass automatic overlap trimming. Existing grouped settled text now offers one editor per durable passage; speaker assignment retains clicked card ids. Unidentified adjacent passages have separate assignment triggers.

Commands and logs: ~/Documents/Codex/2026-09-28/moss-gemini/evidence/P75/edit-client/{base-prototype-final-red.log,frontend-full.log,typecheck.log,build.log,browser-regressions.log,saved-reading-green.log,TEST-RESULTS.md}.

Real Chrome: 6-second synthetic fake microphone, production Account/capture/storage/routes, port18984; four save paths each one PUT; Cancel/Esc/unchanged outside zero; first original retained and audio/speaker/time unchanged; History reload retains Edited; downloaded Markdown contains edited text; existing/new assignments only one selected id each; two matching ids Rename All while other (unidentified) section unchanged. Screenshots visually inspected. Server stopped. Evidence chrome-result.json, chrome-meeting-initial.json, chrome-meeting-final.json, edited.md, editor.png, speaker.png, edited-history.png.

Harness-only failures retained: APIRequestContext failed to send secure workspace cookie on HTTP; assertions now use authenticated in-page fetch. A legend corner clicked the fixed topbar; outside-save now clicks a visible timestamp. No product/input change to get the final browser verdict.

R1: Rename All uses existing per-speaker routes sequentially. A later request failure leaves already acknowledged names visible and the popup error; retry can finish. Real providers, physical devices and deployed-host behavior remain UNMEASURED.

Final verdict: DONE, local candidate only. Full backend gate used the locally built client bundle; generated assets restored afterward and never committed. Shipping needs the lead’s normal rebuild. Client candidate product a4b2f95f; server candidate product 6ba99407; server throwaway 25791c2e; local integration ea6ce764. Bench runs no provider; all servers stopped.
