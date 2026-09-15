# Handoff — finish attended G7, then stress-test the product

Written 2026-09-14 23:40 EDT. The operator is AFK. Two jobs for the next session(s):

1. **Orchestrate and finish the outstanding work** — the attended G7 run is staged and ready to launch.
2. **Stress-test every aspect of the product** in a browser (see §6). This has never been done; every
   browser exercise so far has been the acceptance harness, not adversarial human-style use.

Read this file, then `~/.claude/projects/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/memory/auto-mvp-0911-progress.md`
(round-by-round state, last entries current) and `auto-mvp-0911-mandate.md` (authorities, gate tolerances,
GitHub identity, the audio ruling).

## 1. Ready to launch right now

`501c55ca62fd77161f62aaff9e208b0921eb166a` is **staged inert and verified** on the host: manifest SHA matches,
all three `candidate_manifest` refs repointed with none stale, `chrome_cdp_endpoint` preserved, vLLM **PID 369**
untouched, Phase-1 serving, 672 G free. The operator's Chrome and `ssh -R` tunnel are alive with **exactly one
page** (the podcast tab — do not leave a second MOSS tab open, see §4).

```bash
ssh gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
wsl.exe -d Ubuntu -u devcontainers
tmux new -s live
```
```bash
SHA=501c55ca62fd77161f62aaff9e208b0921eb166a
CUTOVER="$HOME/.local/share/moss-transcribe-diarize/account-runtimes/$SHA/bin/mtd-phase2-cutover"
export PYTHONDONTWRITEBYTECODE=1
ATTEMPT="$HOME/.local/state/moss-transcribe-diarize/cutover-attempts/preadmission-$(date -u +%Y%m%dT%H%M%SZ)"
printf 'Attempt: %s\n' "$ATTEMPT"
"$CUTOVER" run --profile "$HOME/.config/moss-transcribe-diarize/moss-cutover.json" --attempt "$ATTEMPT" --terminal preadmission --skip-qualification
```

`--skip-qualification` (`aaf10d02`) skips re-measurement and goes straight to the attended canary: **~2.5 min to
the picker** instead of ~2 h. The operator has ordered that re-qualification is never proposed again.

**Before launching, clear the operator's Chrome HTTP cache over CDP** (`Network.clearBrowserCache`). Their
profile still holds Phase-1's assets from tonight; `501c55ca` makes that harmless, but the demo run should not
be the first live test of that fix.

## 2. G7 status — one behaviour away from passing

Attempt `preadmission-20260915T021913Z` on `d8e04a9b`: **scenario 1 `microphone_meeting_tab` passed end to end**
(first ever) and `validate_attended_g7` accepted it. **Scenario 2 failed on exactly one field**:
`distinct_speakers == 1`. Meeting was 23.2 s, status `completed`, audio `available`, MP3 16 k/mono/48 k — all
correct.

**The only change needed: at prompt 2, wait until TWO speaker labels are visible before pressing Enter.**
The operator pressed at 23 s when only one podcast host had spoken. Allow 40–60 s.

**G7 and the demo have different requirements — do not conflate them:**

| | needs | operator's voice transcribed? |
|---|---|---|
| G7 gate | both *meters* live + two distinct speakers | **no** — the two-host podcast supplies both |
| client demo | operator's voice in the transcript | **yes** — so never overlap sources |

**Gate weakness, recorded not fixed:** `distinct_speakers >= 2` can be satisfied entirely by shared audio, so
G7 does not verify the microphone lane contributes speech. Tightening it would make a blocked gate harder to
pass; raise it with the operator after the demo.

## 3. The product blocker (diagnosed, NOT fixed)

**The v2 mixer collapses both lanes into one mono ASR input.** Mic and system each get −6 dB and are summed into
a single PCM buffer (`app/live_mixer.py:267`); the decoder only ever sees that mix
(`live_coordinator.py:534→558`). When both talk at once the decoder transcribes the **cleaner** lane (shared
tab) and the presenter's voice is lost. Ingestion is clean (`live_transport.py:481`); raw lanes are
intentionally discarded (`phase2_audio.py:71`).

Proven by downloading the real Acquired feed, correlating (0.918–0.974), fitting gain (−6.7 dB) and subtracting
it — the residue decoded as the operator's counting. **Gain cannot fix it: +6/+12/+18 dB all stayed
podcast-only.** AEC is exonerated (Headphones was selected; confirmed in an operator screenshot).

Full diagnosis and a no-cutover probe: `prototypes/streaming-diarization/microphone-mix-loss/{probe.py,NOTES.md}`
and `docs/design-streaming-diarization.md:360`. Proposed fix **O1** (retain aligned lane PCM, sequence the lanes
into one decoder request, remap timestamps, namespace speakers) recovered both sources in 2.543 s but still
duplicated podcast words in some spans — **deliberately not shipped**, since it would bypass unchanged quality
gates.

**Operator ruling: demo without overlapping audio.** Speak → play the shared tab → speak. `docs/handoffs/demo-script.md`
already follows this. The eventual target (built-in speaker + built-in mic) needs both O1 *and* working AEC —
see the audio ruling in the mandate memory.

## 4. Traps that have each cost an attended attempt

- **Never Ctrl-C a running cutover.** It stranded the host once and required a manual restore of the 6
  `mutation_*` snapshot roles. `restore` refuses terminal attempts by design.
- **The canary drives the whole UI itself** — it opens its own tab, selects Listening setup, and clicks *Enable
  microphone*, *Share audio*, *Start capture*, *Stop*. The operator must touch **only** the Chrome share picker,
  make noise, and press Enter. A stray second MOSS tab shares the cookie jar and destroyed one run.
- **Chrome with zero windows** still answers `/json/version` 200 but has no browser context, so `connect_over_cdp`
  fails with *"Browser context management is not supported"*. Preflight must check `/json/list` for a real page.
- **`tail -F` the printed attempt path**, never a re-derived one — `$(date)` in a second shell produces a
  different timestamp.
- **Push only to `private`.** `origin` is a PUBLIC fork; a codex agent pushed a branch there tonight and it had
  to be deleted. On 404, `gh auth switch --user yugao-aisight`.

## 5. Outstanding work, in priority order

1. **Launch and pass G7** (§1, §2). On PASS the candidate keeps serving `:7861` — that is the demo state.
2. **After G7 passes:** presenter voiceprint enrolment, `scripts/demo-precheck.sh <FULL_SHA>`, operator smoke
   rows (`docs/handoffs/e2e-smoke-for-operator.md`), then rehearse `docs/handoffs/demo-script.md`. All require the
   candidate serving.
3. **Bring records current** — `docs/handoffs/auto-mvp-0911-handback.md` and PR #32 predate ADR-0014 and several
   SHAs. PR #32 stays **draft/unmerged**.
4. **Deferred, not for the demo:** mixer fix O1; AEC for the speaker-output target; the G7 two-speaker weakness;
   `fix/prestart-error-consolidation` (`bc4950c4`, on `private`, unstaged — apply only if diagnostics point there);
   pre-existing `test_finalization_failure_stop_boundary[decode_failed]` (fails on a clean tree; host status unknown);
   no Let's Encrypt renewal automation (cert expires **2026-12-09**).

## 6. Stress testing — the operator's second ask

Nothing has adversarially exercised the product in a browser. Do this **against the candidate once G7 passes**,
or against an isolated local stack; **never** start a capture while a cutover is running. Use the
`claude-in-chrome` skill (or Playwright against the operator's CDP endpoint).

Worth attacking, informed by what has already broken: live capture start/stop/restart; Stop pressed twice
quickly; tab hidden/backgrounded mid-capture; network blips; reshare and device switching mid-session; file mode
with mp3 plus non-mp3 rejection; export md/txt/json/SRT/VTT; audio download complete and interrupted; speaker
rename propagation and "Save voiceprint"; meeting history at scale and after reload; the LLM relay against both
upstreams and with one down; phone-width layout (~400 px); and the two just-fixed UI defects — duplicate history
node and stale-asset rendering across a deployment change.

Report defects with file:line and evidence. Do not weaken `QUALITY_BOUNDS`, the identity policy, or any gate.

## 7. Agents

Codex agents stand by in tmux `MOSS:1.2`, `2.1`, `2.2`, `2.3`, `2.4`; they take plain-English tasks via
`tmux send-keys` followed by a separate `Enter`. **`2.1` is the host owner** — the only pane with the SSH/WSL
wrapper; it does all staging. `2.2` reviews. `2.3`/`2.4` implement and investigate. Send high- and medium-risk
fixes to them per the operator's instruction. Give each the established evidence so it does not re-derive.

**Suggested skills:** `claude-in-chrome` (§6), `diagnose` (if an attended run fails for a new reason),
`tmux-peer` (reading codex panes).
