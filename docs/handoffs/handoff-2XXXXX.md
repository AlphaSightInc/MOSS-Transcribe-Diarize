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

**SUPERSEDED — use `628341fad9399c897e26fe3e5f11f0e087eeafe0`, see the UPDATE block above.** Note the branch
head is `a46b05a8`, which differs from the staged SHA by **docs only**; do not restage for that.

`628341fad9399c897e26fe3e5f11f0e087eeafe0` is **staged inert and verified** on the host: manifest SHA matches,
all three `candidate_manifest` refs repointed with none stale, `chrome_cdp_endpoint` preserved, vLLM **PID 369**
untouched, Phase-1 serving, 672 G free. The operator's Chrome and `ssh -R` tunnel are alive with **exactly one
page** (the podcast tab — do not leave a second MOSS tab open, see §4).

```bash
ssh gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
wsl.exe -d Ubuntu -u devcontainers
tmux new -s live
```
```bash
SHA=628341fad9399c897e26fe3e5f11f0e087eeafe0
CUTOVER="$HOME/.local/share/moss-transcribe-diarize/account-runtimes/$SHA/bin/mtd-phase2-cutover"
export PYTHONDONTWRITEBYTECODE=1
ATTEMPT="$HOME/.local/state/moss-transcribe-diarize/cutover-attempts/preadmission-$(date -u +%Y%m%dT%H%M%SZ)"
printf 'Attempt: %s\n' "$ATTEMPT"
"$CUTOVER" run --profile "$HOME/.config/moss-transcribe-diarize/moss-cutover.json" --attempt "$ATTEMPT" --terminal preadmission --skip-qualification
```

`--skip-qualification` (`aaf10d02`) skips re-measurement and goes straight to the attended canary: **~2.5 min to
the picker** instead of ~2 h. The operator has ordered that re-qualification is never proposed again.

**Before launching, clear the operator's Chrome HTTP cache over CDP** (`Network.clearBrowserCache`). Their
profile still holds Phase-1's assets; `628341fa` makes that harmless, but the demo run should not
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
