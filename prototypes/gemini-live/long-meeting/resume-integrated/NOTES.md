# P74-RI integrated measurement

1. Question: does the built browser plus real server preserve capture ownership and the meeting timeline through reload?
2. Primitives: page identity owns writes; lease bounds return; lane sequence/epoch orders audio; mixed-clock intervals preserve missing time; saved document and views expose it. Each answers a separate observable requirement.
3. Invariants: one meeting/writer/archive; gaps are silence and metadata, never speech; live/History/browser text exports agree; terminal meetings stay terminal.
4. Unknowns: physical devices, native picker, provider continuity, host deployment. Chrome chooser automation bypasses gesture policy; inject only gestureless display refusal to measure the specified silent-system branch.
5. Falsifier: any A–I requirement fails on integrated a6117c0a. Stop that case, retain failure; no product fixes.
6. Tools: existing Phase-2/test provisioning and scripted recognition seams; built assets without rebuild; real Chrome with fake devices and real UI; capture receipts and decoded MP3 for exact clock; existing L1 product loop for request budget. No real provider/key/host.

Run from worktree root:
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/long-meeting/resume-integrated/run.py`

Full observations, saved documents, browser downloads and screenshots go to the named evidence root. The lease remains 120 seconds; C advances the server's presence/failure monotonic clock by 125 seconds. Summary generation uses a local fake callable, capturing both the browser request and the real server's speech-only generator document. No protocol stand-in.

Verdict: pending.

Final verdict: **PASS A–I**, real server + integrated built assets, Chrome 154.0.8037.98, fake media/scripted recognition. A/B first accepted frame 3.074/3.086 s, 0 clicks; B share 1 click and 4 non-silent system frames. A/B one MP3 27.3740625/15.2450625 s, zero interior gap PCM and exact mixed samples, canonical saved gaps + 16000 Hz. F two ordered gap lines. C virtual +125 s clock refused, interrupted. D viewer after 17 attempts/8.028 s while original gains 36 frames. I explicit takeover fences original/ends tracks/viewer without new meeting; click to frame 0.554 s. G normal one 4.500 s archive/document-only segments. H 100002 loop requests (100003 responses including setup heartbeat), 0 failures, 98.626 s. MD/TXT and summary separation pass.

Evidence: `/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume-integrated/result.json`; browser `chrome-20261002-151011/`, H `H-product-a6117c0a.json`; complete plain report in P74-RI-STATUS.md.

Retain tooling failures: import-path failure preceded all cases; G whole-body assertion incorrectly included older History cards. Correct G using same-run screenshot/current document/decoded archive, no recording rerun. Raw result-raw-chrome.json preserved; future runner scopes transcript nodes. The one-command runner was consolidated afterward to invoke the existing H runner itself; syntax checked, consolidated orchestration not rerun. The measured browser cases and H ran separately as receipts show. No product edits or benchmark-result tuning. All own listeners closed. Physical/native picker/provider/host/real-time endurance remain unmeasured. Product size 0 lines. Disposable files retained uncommitted; no push.

## P74-RM requalification contract

1. Question: do production labels/text edits/Speaker popup/History deletion coexist with same-meeting resume?
2. Primitives: durable passage (text and section assignment); separate mixed-clock gap interval; one leased page writer; persisted meeting; browser render/export. Each owns a distinct required effect.
3. Invariants: gaps stay noneditable and outside speaker/summary input; edits retain gaps/audio/times; active/leased meetings reject edit/delete; R4 late start has no gap; R5 pre-adoption partial chunks are discarded; all A-I controls retain meaning.
4. Unknowns: physical media/picker, real providers, host/network deployment, real-time 45-minute endurance. Gestureless display refusal injected; 120 s lease unchanged; C advances only server clock.
5. Falsifier: any A-L assertion fails. Preserve raw failed receipts; diagnose before any correction, label harness vs product change. No provider calls.
6. Tools: existing integrated runner + L1 real product request loop; actual Chrome/Phase-2 app/scripted recognition and fake summary. Worklet observer records frame starts without modifying messages. J reloads before first frame; K measures partly filled real worklet frames at adoption; L uses actual edit/Speaker/export/delete UI. Full suites detect regressions outside these cross-feature cells.

Command: `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/long-meeting/resume-integrated/run.py`
Evidence: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume-merge/`. Product merge and throwaway runner are separate commits. RM verdict pending.

### RM composition defect: gap is a visible speaker-block boundary

Question: can an interruption split cards but leave their Speaker controls hidden?
Primitives: the existing row, gap interval and continuation flag; no new state or threshold.
Invariant: a completed gap between rows ends presentation continuation, even for the same voice. Ordinary same-speaker guess continuation stays unchanged. Unknowns: no new provider/device claim.
Falsifier: the production projector still marks a post-gap row as continuation, or a no-gap control changes.
Tool decision: row-boundary.ts calls the actual production projector, then applies the one-condition candidate in process and prints full rows/control counts. A measured failure licenses the narrow projector fix; DOM/native Chrome verify actual visible controls.

Prototype command: `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/long-meeting/resume-integrated/row_boundary.py` (builds and runs actual product projector; full state printed).

Prototype verdict: baseline has 1 hidden post-gap speaker block; candidate 0; ordinary guess continuation true and no-gap control byte-identical. Two production regressions red (projector + DOM continuation attribute). Narrow product correction adds the same gap boundary to continuation, then real Chrome L must click the now-visible section Speaker button without force. Original K observer read retired worklets; corrected K delays real resume response by 250 ms after new worklets start, with no protocol/message change. Failed raw receipts retained.

L harness refinement: the production one-speaker popup already opens New Speaker; a blind combobox click closed it. Use its aria-expanded state and textbox role, as the shipped P75 flow does. Failed L receipt retained. Product correction is only the gap/continuation boundary; no popup changes.

### Archive-clock qualification failure (strict gate retained)

Question: does the decoded MP3 discrepancy reflect missing/extra mixed PCM or codec padding? Primitives: authoritative mixed sample count, staged PCM sample count, decoded codec output. Invariant: capture/archive prefix must keep all mixed samples; padding must not be claimed as speech loss or exact equality. Unknown: encoder padding behavior at the measured non-frame-aligned lengths. Falsifier: product archive encoded from exactly known synthetic input reproduces or refutes the discrepancy; complete live publication already requires staged PCM==runtime count. Tool decision: archive_clock_probe.py calls actual MeetingAudioArchive at frozen failed lengths 437770/321422 and prior passing controls 437985/243921/56000. No change to gate or codec.

Command: `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume-merge/archive_clock_probe.py`. Raw final Chrome failures A/E +37 samples, F +33 retained; verdict pending probe.

Archive verdict: **strict E/F qualification FAIL**, not capture sample loss. Actual product archive at exactly known synthetic inputs reproduces 437770 -> 437807 (+37) and 321422 -> 321455 (+33); old controls 437985/243921/56000 decode exactly. First/last MP3 packet side data reports skip_samples=1105 and discard_padding=576 on the failed 437770-sample case. No audio-codec code changed; no tolerance/gate relaxed. This is an inherited codec-tail boundary exposed by arbitrary resumed sample lengths. Correction lies outside this named merge work package; lead must decide codec scope/qualification policy. Final full A-L receipt chrome-20261002-164854 retains E/F FAIL; A/B capture, C/D/G/H/I/J/K/L PASS. Candidate remains unqualified.

RM final verdict: **BLOCKED on strict MP3 archive qualification**, source merge/tests complete. Frontend 641/42 files, typecheck/build pass; backend 2998 passed/9 skipped/2 xfailed/37 subtests, 440.98 s. Final Chrome A/B/C/D/G/H/I/J/K/L PASS, E/F FAIL; H 100002 loop requests (100003 responses) zero failures, 89.544 s. A/B recovery 3.601/3.063 s, zero resume clicks; B one share click. K actual partial worklets 4480/8000 samples each, 10/10 accepted frames, zero 400, original tracks ended. J 56000 samples/lane sent = decoded, zero gaps. L native visible Speaker click, section assignment (nine durable passage IDs), edit/History/Markdown/gap/delete all pass. A/F +37/+33 codec tails independently reproduced at exact frozen PCM lengths. Raw negatives retained; no tolerances or codec changes.

Final evidence: chrome-20261002-164854/result.json, archive-clock-probe/result.json, backend-full-final.txt, frontend-full-final2.txt, typecheck-final2.txt, build-final2.txt. Screenshots B-silent-system and L-edited-speaker visually checked. Own Chrome/servers closed; generated assets restored and excluded. Source commit custody and all nine conflict resolutions in P74-RM-STATUS.md. No push/provider/key/host/production-state actions; initial inherited full-suite ephemeral binds were interrupted and bounded thereafter (recorded deviation).
