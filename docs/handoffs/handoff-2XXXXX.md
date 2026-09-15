# Handoff — finish attended G7, then stress-test the product

Written 2026-09-14 23:40 EDT. The operator is AFK. Two jobs for the next session(s):

1. **Orchestrate and finish the outstanding work** — the attended G7 run is staged and ready to launch.
2. **Stress-test every aspect of the product** in a browser (see §6). This has never been done; every
   browser exercise so far has been the acceptance harness, not adversarial human-style use.

> ## UPDATE 2026-09-15 11:45 EDT — read this first
>
> **The product is green; the demo is blocked on three operator actions.** Since this doc was written:
> the candidate advanced to **`628341fad9399c897e26fe3e5f11f0e087eeafe0`** (staged inert and verified),
> the full e2e suite ran **six times clean** (13/14 then 13/13 ×5 incl. a 3-run soak), both UI defects plus
> a third (unversioned audio worklet) are fixed and verified live, and the **non-overlapping demo path is
> proven end to end** (two distinct voices → `speaker-0001` tab / `speaker-0002` mic).
>
> **Measured on the staged build** (local stack, 50 s corpus): first text **0.34 s**, segment latency p50
> **2.95 s**, label delay p50 **2.99 s**, final **WER 0.0708** (bound 0.0951). Caveat: measured over an SSH
> tunnel to the host vLLM and without the host profile's `draft_lane_seconds=1.0`, so the demo host should
> be no worse.
>
> **Microphone root cause CORRECTED — it is LEVEL IMBALANCE, not the mixer architecture.** At lane parity
> both voices transcribe; at the operator's real ~3 % mic level the mic voice vanishes. The earlier
> "gain cannot fix it" finding was unsound (it amplified an already-mixed recording). Fix on branch
> `fix/lane-level-balance` (`6a181eb2`, private only, **not staged**) recovers the voice, leaves the
> non-overlap case identical, and raises admitted identities on parity-overlap from 1 to 2. Its effect on the
> gated macros is being measured locally; **do not stage it for the demo**.
>
> **BLOCKERS, all operator-side:**
> 1. **G7** — attended; needs a human at the Chrome picker with a live mic. Cannot be automated: the canary
>    refuses the fake-media/auto-accept switches by design.
> 2. **`ga0-rtx4090:1235` LLM server is DOWN** (host pings, nothing listening). Sole cause of e2e row 9
>    failing and required by `demo-script.md`'s two-model check. That box is read-only per the mandate.
> 3. **`m4mbp.local` was offline at 11:46** — laptop asleep, so the `ssh -R` CDP tunnel is gone too.
>
> ### G7 when the operator returns — four attempts failed on PROCEDURE, not product
> 1. Chrome must have **≥1 window open** — a zero-window Chrome still answers `/json/version` 200 but has no
>    browser context, and `connect_over_cdp` fails "Browser context management is not supported". Check
>    `/json/list` for a real page, not `/json/version`.
> 2. **Do not leave a MOSS tab open** in that profile. Leave only the podcast tab. A second MOSS tab shares
>    the cookie jar and re-bootstraps the workspace out from under the canary.
> 3. **The operator must not click anything in the MOSS UI.** The canary opens its own tab and clicks
>    Listening setup, Enable microphone, Share audio, Start capture and Stop itself. The operator's only jobs
>    are the Chrome picker, making noise, and four Enters.
> 4. **At prompt 2, wait until TWO speaker labels are visible** before pressing Enter. The last attempt died
>    here: Enter at 23 s with only one podcast host having spoken → `distinct_speakers == 1`.
> 5. **Never Ctrl-C.** It stranded the host once and needed a manual restore of the 6 `mutation_*` roles.
> 6. Both meters must be non-zero **simultaneously** to reach `capture-phase=ready`; overlap the sources
>    rather than alternating, and have sound flowing *before* the first Enter (the sample starts at the
>    keypress).
> 7. Note the gate weakness: `distinct_speakers >= 2` can be satisfied by the two-host podcast alone, so G7
>    can pass without the operator's voice ever transcribing. That is fine for the gate, not for the demo.
>
> Launch is unchanged apart from the SHA — use `628341fa…` with `--skip-qualification` (§1).

Read this file, then `~/.claude/projects/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/memory/auto-mvp-0911-progress.md`
(round-by-round state, last entries current) and `auto-mvp-0911-mandate.md` (authorities, gate tolerances,
GitHub identity, the audio ruling).

## 1. Ready to launch right now

`566024287cdd02204f26ac6a83e2c22ef1c90a7c` is **staged inert and verified** on the host (2026-09-15 17:58 EDT, codex
2.1): manifest SHA exact with `activation_state=staged_inert`; all three `candidate_manifest` refs repointed, none stale;
`chrome_cdp_endpoint` preserved (`http://127.0.0.1:9222`); vLLM **PID 369**, `NRestarts=0`, untouched; Phase-1 serving;
both disk guards pass. The `628341fa` runtime is kept for rollback. Retention pruned `501c55ca`; restage its pushed SHA if
it is ever needed.

It supersedes `628341fa`, whose Final Summary failed realistic-length meetings: models misconverted float-second
timestamps (59.64 s -> `00:59:64`), and Gemini also wrapped its JSON in markdown fences. The fixes are `d53ecd99`
(timestamps sent as HH:MM:SS; `response_format` for external providers) and `56602428` (precheck probes made optional).
In a real browser: Gemini 2.5 Flash via OpenRouter was current on 50 s and 180 s transcripts every time.

**The client side is NOT ready: `m4mbp` is offline.** When it wakes, re-verify before launching:
- Chrome has at least one window — check `/json/list`, because a zero-window Chrome still answers `/json/version`.
- The `ssh -R` tunnel reaches WSL.
- Exactly one page is open, and it is not a MOSS tab (§4).
- Clear Chrome's HTTP cache over CDP (`Network.clearBrowserCache`).

```bash
ssh gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
wsl.exe -d Ubuntu -u devcontainers
tmux new -s live
```
```bash
SHA=566024287cdd02204f26ac6a83e2c22ef1c90a7c
CUTOVER="$HOME/.local/share/moss-transcribe-diarize/account-runtimes/$SHA/bin/mtd-phase2-cutover"
export PYTHONDONTWRITEBYTECODE=1
ATTEMPT="$HOME/.local/state/moss-transcribe-diarize/cutover-attempts/preadmission-$(date -u +%Y%m%dT%H%M%SZ)"
printf 'Attempt: %s\n' "$ATTEMPT"
"$CUTOVER" run --profile "$HOME/.config/moss-transcribe-diarize/moss-cutover.json" --attempt "$ATTEMPT" --terminal preadmission --skip-qualification
```

`--skip-qualification` goes straight to the attended canary: about 2.5 min to the Chrome picker.

**After PASS, before the demo:**
- In the presenter's browser, open *Optional AI summaries* and set Provider to **External HTTPS provider**, URL
  `https://openrouter.ai/api/v1`, Model `google/gemini-2.5-flash`, and the operator's OpenRouter API key. Then *Save on
  this browser*. The key lives only in that browser profile, never on the server. It was pasted into a chat session, so
  rotate it after the demo.
- Go/no-go: `MOSS_DEMO_OPENROUTER_API_KEY=<key> scripts/demo-precheck.sh 566024287cdd02204f26ac6a83e2c22ef1c90a7c`.
  rtx4090 is probed only when `MOSS_DEMO_RTX4090_BASE` is set.
- Summaries regression for the demo provider: `MOSS_SUMMARY_PROVIDERS=external OPENROUTER_API_KEY=<key>
  .venv/bin/python tests/e2e/verify_summaries.py`, with `MOSS_BASE` set to the demo origin. Do not switch the demo to
  the relay: qwen still fails about a third of 180 s summaries on timestamp format (see that file's docstring).

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

## 3. The product blocker — **THIS SECTION IS SUPERSEDED, see the UPDATE block above**

> The conclusion below ("gain cannot fix it") was **disproved on 2026-09-15**. The +6/+12/+18 dB arms
> amplified an *already-mixed* recording, in which the microphone was already buried — amplifying a mix
> cannot unbury it. Boosting the **mic lane before the sum** was never tested, and direct measurement shows
> lanes at parity transcribe both voices while a 3 % mic lane loses one. The real cause is **level
> imbalance**, and the fix is `fix/lane-level-balance` (`6a181eb2`). The text below is retained for the
> file:line map of the mix path, which remains accurate.


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

## 5b. Branch rulings — settled 2026-09-15, do not relitigate

A controlled A/B on the local stack (worktree `-wt-auto-mvp-0911`'s sibling `-wt-localstack-0911` checked out per
branch, stack restarted between arms, one probe, one corpus) settled the four parked fix branches. Evidence is in
memory `auto-mvp-0911-progress.md` under the 2026-09-15 12:55 entry.

**The demo path is safe on the staged build — no fix required.** Non-overlapping lanes with the microphone at 3 %
of full scale (the level the 2026-09-14 attended run measured from the MacBook built-in microphone) yields two
speakers, both fully transcribed, on `628341fa` itself. This had only ever been proven at full microphone level
before, and it was the last real doubt about the presenter being heard. Re-runnable any time:

```
.venv/bin/python tests/e2e/verify_demo_lanes.py --allow-local-self-signed    # exit 0 = demo path intact
```

| branch | ruling |
|---|---|
| `fix/lane-preserving-asr` (`7e5a2ad2`) | **Do not land.** Under overlap + quiet microphone it moves `identities_born_count` 1→2 but the committed transcript is **byte-identical to baseline** — 8 segments, 79 words, all `speaker-0001`, zero microphone words. It buys identity accounting, not recovered speech, across 494 lines in four runtime modules. And `identities_born_count` reads 2 even when the microphone lane is pure silence, so even that one effect is not a real signal. |
| `fix/lane-level-balance` (`6a181eb2`) | **Do not land.** Already measured: the gain amplifies the noise floor. |
| `fix/prestart-error-consolidation` (`bc4950c4`) | Post-demo. Genuine fixes (first error wins, no silent restart, chooser kept inside the user gesture) but it would **not** have changed the failed attended run — in that hang there is no error at all, one lane simply delivers digital silence. Older base (`d8e04a9b`), needs a frontend asset rebuild. |
| `fix/frame-sample-rate-validation` (`3d831f36`) | Post-demo hardening. 14 lines, verified against a running service, low risk. |

**Operator defect (1) — "no popup, no indication, ran on for 120 s" — is already fixed; do not rebuild it.** The
per-lane hint (`data-capture-readiness`, `ControlPanel.tsx:366`) names the silent lane, and it was present even in
the failed candidate `1d583842` (introduced by `24b48395`). The operator could not *see* it because of the
stale-CSS corruption, which `628341fa` fixes by versioning assets. Regression coverage already exists at
`frontend/src/components/ControlPanel.test.tsx:152-163`. The readiness gate is `rms > 0` on both lanes
(`ControlPanel.tsx:68`, `:317`) — exactly `0.0` only for a paused tab or a muted microphone. That strictness is
deliberate: leave it alone.

Frontend suite on `628341fa`: 24 files / 205 tests, all pass.

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
