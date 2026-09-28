# DRAFT — Handoff: MOSS round 7 (from round 6, 2026-09-24)

**Historical record:** H1 #3 qualified freeze-4 (`8d8fb682`) with 0 errors; Phase-1 was restored. The next A4/H3 must use qualified freeze-5 (`<FREEZE-5 SHA>`) after the lead verifies staging and host gates. A4/H3 remain pending in this draft. The MVP verdict and admission remain the user's decisions.

Read first: [round-6 closing draft](/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/moss-mvp-review/round6-closing-report-20260924.md).
Decisions: `grilling-decisions-20260923.md` (D36–D48) beside that report; plan `round6-critical-path-20260923.md`.
**R6** below means `/Users/gao/Documents/Codex/2026-09-23/moss-round6/`. Its `status/INTEGRATION-STATUS.md` is the authoritative timeline; `status/ASK-PLANNER.md` has the latest relayed decisions. Host state below is recorded there / in the Phase-4 brief, not freshly surveyed by this documentation task.

## State

- **F1 — Candidate:** `round6/integration` in `/Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate`, full SHA **`8d8fb682884bd29369879698d8233a1b281b77d7`**, tag `round6-frozen-20260923-4`; local checkout clean and peeled tag verified while drafting. Ledger records private push completed and GitHub account returned to `AlphaSightInc`. No merge into `dev` or `auto-mvp-0911` is authorized here.
- **F2 — Host:** `ga0-alienware-rtx4070ti`; Windows SSH user `gyauo`, WSL Ubuntu user `devcontainers`. Phase-1 live on **:7861/:7860**; internal open-workspace instance **:7862** restored on runtime `18e8a035`; all four services recorded active, endpoints HTTP 200. **vLLM PID 369, NRestarts 0**. `account-current` absent; candidate staged inert, four profile references point to the frozen SHA. Source: ledger terminal H1 #3 and A4-prep entries.
- **F3 — Retention:** **8 retained runtimes, keep=8** per `briefs/PANE-3.1-PHASE4-REPORT.md`; stage with **`MOSS_RETAIN_CANDIDATES=8`**. Keep `18e8a035`: a previous prune broke :7862 for ≈05:29–06:44 EDT. The runtime inventory is supplied handoff state, not a new host count.
- **F4 — Qualification:** H1 #3 `qualified=true`, errors empty, deterministic 18/18 (Python 2,416 passed / 0 failed), deployed 19/19, pre-admission 17/17; **G7 UNCLAIMED, admitted false**. Terminal `restored`, reason `planned_post_qualification_restore`. H1 #3 is attempt **2/3** under D47 despite three physical rehearsals. Evidence: R6 `evidence/r6-h1c-20260924T013646Z/`; report `evidence/h1-report/h1c-report.md`.
- **F5 — Resources:** GPU lease file reads FREE. Ledger closing spend **≈30,207**, including round-5 carry 4,784; round-6 run additions sum to **25,423**. H1 runs: 8,161 / 8,196 / 8,186; D45 replay 728; focused/file 137 / 15. Provider ledger 8/10, H3 not spent yet. New decoder work needs its applicable authority; this handoff supplies none.
- **F6 — Changes:** H1/H2's service-product fix is status response **16 KiB → 1 MiB** (request cap unchanged); the earlier A4 null-bundle cutover fix also shipped. Other qualification repairs concern tests, collectors, validators and approved measurement semantics. D45b preserves raw DER beside the uncertain-speaker projection; D46 credits rolling or proven final-pass coverage. No acceptance-bound widening.

## Next: freeze-5 A4, then H3 demo-precheck

**A4 remains pending.** Lead first verifies that the qualified, staged build, host precheck/launch scripts, and candidate profile all resolve to the same full `<FREEZE-5 SHA>`. The freeze-4 commands and H1 #3 facts elsewhere in this draft are historical; do not run them for freeze-5. The MacBook operator uses the one-screen [A4 checklist](/Users/gao/Documents/Codex/2026-09-23/moss-round6/briefs/attended/A4-OPERATOR-CHECKLIST.md) and [CDP runbook](/Users/gao/Documents/Codex/2026-09-23/moss-round6/briefs/attended/A4-MACBOOK-CDP.md).

MacBook route: headphones and built-in microphone; one speech video tab in a dedicated Chrome profile with loopback Chrome DevTools Protocol (CDP) on port 9222. Keep the reverse tunnel open:

```sh
ssh -N -R 9222:127.0.0.1:9222 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
```

Confirm CDP shows exactly one page, then tell the lead **“tunnel up.”** Before launch, use T4 for the **10-second echo check**: `ssh -t gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us wsl.exe -d Ubuntu -- tmux -L a4echo attach -t a4echo`; type `ok` and Enter, see `RECEIVED 'ok'`, detach with `Ctrl-b d`, and tell the lead **“echo ok.”** This proves the Enter keys will reach the host tmux pane.

After the lead's same-SHA precheck and launch, attach T4 with `ssh -t gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us wsl.exe -d Ubuntu -- tmux -L a4 attach -t a4`. Give **8 Enters: 4 for tab audio plus mic, 4 for Entire screen/System Audio plus mic.** In each scenario: both meters moving; pause video and say the checklist phrase alone; stay silent until shared speech appears; then overlap speech until both speakers appear. Enter after each step. If T4 cannot take Enter, operator says “Enter” on the call and the lead uses host `tmux -L a4 send-keys -t a4 Enter` for each prompt. Detach with `Ctrl-b d`, never Ctrl-C.

**Freeze-5 view to watch:** With headphones and the built-in mic, first text should appear within about 4 s after Live opens and speech starts. Unsettled speech that starts a card says **Remote** (shared audio) or **You** (mic); an unsettled continuation stays in its settled speaker's card with dashed/amber styling. One **Identity settling** hint; no draft text or **Speaker uncertain** row. A quiet mic lane produces no rows. The 60 s pass can settle names about 30–60 s after speech; the 150 s pass can refine them about 2–2.5 min later and may rename once. Settled rows use distinct styling and consecutive speaker numbers unless named; nearby turns can share a card while retaining both passages. A voiceprint needs at least 2 s of admitted, clear speech. If Save voiceprint is refused, one **Save name** click still applies the name without a voiceprint and shows a plain note. Report a mismatch to the lead; this view alone does not establish A4 PASS.

**A4 PASS** requires the lead to see `attended_g7_complete`, `attended-g7.json`, terminal `preadmission`, `g7=PASS`, `admitted=false`, the same `<FREEZE-5 SHA>` serving trusted `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861`, and unchanged vLLM identity. Record the actual attempt and receipts. If A4 fails, the lead follows the recovery runbook; do not call it PASS from a visible UI alone.

**H3 demo-precheck, MacBook only after A4 PASS.** From a checkout of `<FREEZE-5 SHA>`, read the OpenRouter key **silently** into the environment (never print it or put it in shell history), then run:

```sh
read -rs MOSS_DEMO_OPENROUTER_API_KEY && export MOSS_DEMO_OPENROUTER_API_KEY
if test -n "${MOSS_DEMO_OPENROUTER_API_KEY:-}" && test -f scripts/demo-precheck.sh; then
  bash scripts/demo-precheck.sh '<FREEZE-5 SHA>'
else
  printf '%s\n' 'NO-GO: key or freeze-5 script missing'
fi
```

Replace `<FREEZE-5 SHA>` with the lead-confirmed full SHA. **H3 GO** means the script checked normal HTTPS trust, the served candidate SHA, workspace bootstrap, relay models, and short configured upstream/OpenRouter responses with a nonempty key. Retain only the nonsecret GO/NO-GO receipt; NO-GO goes to the lead.

**D49:** After A4 PASS and H3 GO, freeze-5 keeps serving in preadmission on `:7861` with `admitted=false`; Phase-1 stays stopped. Admission is the user's act. The lead neither admits nor restores without the user's instruction.

## Open decisions and backlog

- **Q1 — Freeze-5 A4 start time and operator:** arrange after the new H1 and host precheck; no freeze-5 attended PASS is recorded in this draft.
- **Q2 — After A4 PASS:** D49 is answered: keep preadmission serving. The user alone decides any later admission or restoration.
- **Q3 — Jamie / MVP:** D36 still needs the short-speaker attended policy record (D37b); D38's tail target is settled. User supplies D30 MVP verdict after the required evidence; engineers do not declare it.
- **Q4 — Handback:** plan's draft PR/history handling remains unmerged and user-governed. This documentation task creates no PR or push; check the current handback record before duplicating another pane's work.

Post-MVP pointer: R6 `status/POST-MVP-BACKLOG.md`, plan §6, and Review `round5-closing-report-20260922.md` §7. Carry owner-history growth, unit-aware runtime retention, residual DER missed-tail versus named-speaker split, terminal observability, inherited N4–N10, S9 visible-word timing, speakers-mode acoustic echo cancellation, relay-summary reliability and tooling hygiene. The backlog file read for this draft covers only the round-6 additions; do not treat absent inherited lines as closed. Native hidden-tab and operator smoke/demo coverage remain as specified in the plan, without a completion claim here.

## Lead shell tooling (R6 `status/*.sh`)

Inventory of the **21 scripts present when drafted**, one line each. Historical run-specific scripts retain old SHAs, paths and comments; they are evidence/reuse references, not a queue to execute. Read their fixed inputs before any separately authorized reuse.

| Script | Purpose / boundary |
|---|---|
| `a4-precheck-host.sh` | Read-only host observations for qualified H1 #3, freeze-4 identity, services, candidate roots, CDP and disk; lead interprets output. |
| `a4-launch.sh` | Attended freeze-4 preadmission via transient `moss-a4` tmux, baseline counter and pane log; operator/precheck required. |
| `h0-stage-recipe.sh` | Mac bundle/scp, then emits host ext4 wheel-build and retention dry-run commands; stops before real stage; inherited retention comments are stale—set keep=8. |
| `h0-verify.sh` | Host staged manifest/profiles, executing release, A4 fix, response cap, services and prerequisites; default SHA is the old first freeze. |
| `h1-probe.sh` | Observe H1 #1 unit, journal phase, vLLM counter/PID and EXIT from its recorded attempt. |
| `h1b-preverify.sh` | Historical H1 #2 freeze-3 readiness observations; not the current A4 check. |
| `h1b-launch.sh` | Historical H1 #2 full restored rehearsal plus sampler, pinned `7f54b12f`; consumes decoder requests and stops Phase-1. |
| `h1b-probe.sh` | Observe H1 #2 unit, journal, counter/PID and EXIT. |
| `h1b-export.sh` | H1 #2 post-EXIT archive; older broader export selection, superseded as a reuse example by guarded H1 #3 exporter. |
| `h1c-preverify.sh` | Freeze-4 H1 #3 readiness observations, runtime listing, empty roots and disk. |
| `h1c-launch.sh` | Historical H1 #3 full restored rehearsal plus sampler on `8d8fb682`; no repeat authorized by this handoff. |
| `h1c-probe.sh` | Observe H1 #3 unit, journal, counter/PID and EXIT. |
| `h1c-export.sh` | Guarded H1 #3 export after EXIT; excludes qualification checkout and acceptance-private from attempt-record selection. |
| `h2-host-deterministic.sh` | Host deterministic suite at deep checkout path with chosen staged runtime/code; inspect each result, including frontend setup; zero decoder. |
| `h2h-g10-host.sh` | Historical isolated host transcript-pane comparison using copied H1 state and pinned reference; local rendering exception is not trusted-origin proof; zero decoder. |
| `h2h4-host-run.sh` | Historical scratch G10 patch gate: base/fixed tests, H1/ordinary meetings, and failing title control; mutates only its prescribed scratch paths. |
| `lead-gate.sh` | Fresh local clone: backend, bundle, frontend, typecheck, secrets count and clean-tree report; prescribed interpreter. |
| `lead-gpu.sh` | Lease/tunnel :18400 lifecycle and sampler (`up`, `idle`, `sample`, `down`); reads/writes shared round-5/6 lease files. |
| `run-focused-r6.sh` | Real focused row-4/demo-lane run then 30-minute file through the lead tunnel; requires exec clone and decoder authority. |
| `side-preflight-host.sh` | Optional isolated :7863 service for summary/overload/quality; real shared-GPU traffic, reviewed settings correction; not selected/run in round 6. |
| `wsl-run.sh` | Mac zsh wrapper transporting a script via Windows SSH into WSL bash; transport only, not a background-job supervisor. |

Additional offline tool: `status/h1-report.py` renders retained content-free H1 evidence; see `status/H1-REPORT-SCRIPT.md`. Its sampler duration and XML denominator are distinct from outage and pytest headline counts. Do not rerun historical campaigns to regenerate documentation.

## Hard rules and process that held

- **R4 — Repository boundary:** never push `origin`; no merge into `auto-mvp-0911`/`dev`. Any separately authorized private push uses `gh auth switch -u yugao-aisight`, verifies remote result, then switches back with `gh auth switch -u AlphaSightInc`. A local documentation edit does not authorize a push.
- **R5 — Secrets/host:** never read or print `~/.config/moss/openrouter.env`; vLLM PID **369 must not change**; never `wsl --shutdown`. No admission without the user.
- **R6 — Runtime custody:** long host jobs use transient `systemd-run --user` units; use **`MOSS_RETAIN_CANDIDATES=8`**, inspect prune candidates and preserve the internal runtime. Export required evidence before staging/pruning.
- **R7 — Evidence custody:** export only after EXIT/terminal record; guard glob matches and `cd`; preserve exact SHA and source operands, count actual decoder traffic, distinguish service-wide counters and approximate family allocation. The ≈111k-file wrong-root export was contained/deleted, not reusable evidence.
- **R8 — Engineering gates:** prototype product changes, reproduce a failing control before repair, independent review plus fresh verification before merge, three attempts then park. Use `sys.setswitchinterval(1e-5)` for race probes; replay consumers when diagnostic event kinds change (D46 lesson). Keep wrong-named-speaker, uncovered-window and pre-Stop-failure controls failing.
- **R9 — Runtime/tests:** local Python `/Users/gao/Documents/Codex/2026-09-23/moss-round6/runtime/venv/bin/python`; for full suites use `PY=$(/Users/gao/Documents/Codex/2026-09-23/moss-round6/runtime/make-clone-venv.sh <clone>)`. Set `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1`; host qualification uses the staged same-SHA runtime. Local/stub proof does not replace host or attended proof.
- **R10 — Scheduling/claims:** check the clock before stamping; label estimates; keep lease FREE until authorized use. Record A4, H3 and user decisions before finalizing either draft; never turn H1 qualification into an MVP verdict.

Sources: R6 ledger, `briefs/COMMON-R6.md`, `briefs/PANE-3.1-PHASE4-REPORT.md`, `status/ASK-PLANNER.md`; Review plan §7. This draft follows `docs/handoffs/handoff-round6-XXXXXX.md` and changes no executable script or host state.
