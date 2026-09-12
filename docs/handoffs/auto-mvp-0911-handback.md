# auto-mvp-0911 — operator handback

Pull request (draft, unmerged, do not merge before deciding on history squash): https://github.com/aiSight-us/MOSS-Transcribe-Diarize/pull/32

Branch: **`private/auto-mvp-0911`**. Read this as an implementation/evidence handback, not an admission certificate. Source reviewed at `09539ad7`; all change-table commits are verified ancestors. Section 2 records round 15; round 16 is the pending confirmation run. Do not infer a PR, merge or admission from this handback.

## 1. What you need to do (in order)

**Recovery complete — verified 2026-09-12:** Ubuntu VHDX moved to
`D:\wsl\Ubuntu\ext4.vhdx`, file length **612,482,678,784 bytes** (not an allocated-space
measurement); C: **622.06 GB free**, D: **171.84 GB free**. New vLLM baseline **PID 324**,
model endpoint HTTP **200**. Both MinerU scheduled tasks (`MinerU-WSL-Keepalive`,
`MinerU-Windows-Watchdog`) **enabled/running**. Phase-1 both views **open, zero work**;
tailnet origin HTTP **200**. Durable `/etc/hosts` prerequisite
`moss-canonical-host.service` runs before both web units and was verified across
controlled WSL shutdown/restart. Follow [Host hygiene](g7-preadmission-runbook.md#host-hygiene--canonical-origin-after-wsl-restart);
never shut down WSL during an attempt. These recovery facts do not authorize round 14.

1. **Wait for the owner’s go and exact qualified, staged SHA.** Then arrange a working host display **and microphone/audio path** for the attended canary. The recorded host inspection found WSLg disabled; it is not a current live check. Follow the [G7 preadmission runbook](g7-preadmission-runbook.md). An X server alone supplies no audio. If enabling WSLg requires `wsl --shutdown`, arrange downtime **before** an attempt: it stops WSL services, including vLLM and Phase-1; allow model reload and verify recovery. Do not restart them during an attempt.
2. **Run attended preadmission from the interactive WSL terminal**, exactly as the runbook specifies. Budget roughly an hour or more for qualification, not a fixed 60–75 minutes. When Chrome opens, handle sign-in/permissions and share tab audio, then entire-screen audio; make both voices audible and answer four Enter prompts. Success leaves the candidate serving `:7861` in **preadmission, `admitted=false`**. A failure normally restores Phase-1; `SAFE_STOPPED` requires the engineer. Verify the durable result; a missing result is not success.
3. **Run the operator smoke from the MacBook**, using [the exact system-trust command](e2e-smoke-for-operator.md). Rows 1,6,11,12 need no decoder or relay; 6/11 check empty-workspace behavior in that selection. Use the populated command there to exercise exports/audio/summaries. Every invocation creates its own workspace; use your separate rehearsed browser profile for the demo.
4. **Prepare the demo, then follow the [10-minute presenter script](demo-script.md).** Verify your name is in **Voiceprints**. If enrolment is pending, provide more sustained speech; a three-second utterance is not a guarantee. Name the confirmed speaker with **Save voiceprint** checked and confirm the bank entry. Have the MP3, YouTube speech tab, headphones and both summary servers ready.

### LLM configuration to verify before the demo

Use the existing staged profile and ask the release owner to verify it; this handback did not read or change current host configuration. The branch’s [relay configuration](../llm-relay.md) is:

```sh
MOSS_LLM_UPSTREAMS='[{"name":"macstudio","base_url":"http://macstudio.tailnet.aisight.us:1234/v1","models":["qwen/qwen3.6-35b-a3b"]},{"name":"rtx4090","base_url":"http://ga0-rtx4090.tailnet.aisight.us:1235/v1","models":["qwen38-27b-mtp"]}]'
MOSS_LIVE_DRAFT_LANE_SECONDS=1.0
```

Keep both configured MacStudio and RTX4090 upstream servers available; their URLs/models are verified configuration, not a current process-health check. In **Optional AI summaries**, select **Provider → Server relay (tailnet models)**, choose **Relay model**, then **Save on this browser**. Fresh settings choose the first model; saved external settings are preserved. Test each model on a completed rehearsal meeting and read the actual successful model beside **Summary ready.** A model listing is configuration, not a health test.

The browser sends the transcript through authenticated same-origin `/api/llm/chat/completions`; no API key is needed. The frontend requests 2048 tokens; relay budgets floor/default to 2048 and cap at 4096. Both configured upstreams accepted `chat_template_kwargs.enable_thinking=false` in the [real-model replay](../audits/relay-thinking-models-20260911.md). A reasoning-only answer gets one bounded retry, never reasoning substituted as an answer. The browser may then try the next listed model once for relay errors. Keep the generating tab open; the successful-model status is transient, not persisted provenance. For an old saved prompt, choose **Restore default prompt**, then **Save on this browser**. Direct **External HTTPS provider** remains supported and browser-owned.

### Content boundary

Keep diagnostic output metadata-only. The [2026-09-12 content-boundary audit](../audits/content-boundary-20260912.md) removed **402 committed evidence files and 16 embedding caches** from transcript, audio, screenshot, relay-body and related content categories, retained **223 content-free evidence files**, tightened the diagnostic writers, and verified that the relay’s production error paths already return fixed codes without retaining upstream bodies. The removals affect the branch tip; the removed files **remain in git history**. No force-push is permitted under this mandate. **Before any PR to `dev`, let the operator decide whether to squash or rewrite `private/auto-mvp-0911`**; this handback authorizes neither operation. Older audits describe historical measurements; removed raw artifacts are not restored or advertised as current evidence below.

## 2. State of the gates (round 15, candidate `767965d7`)

| layer | collected | passed | failed | unmeasured |
|---|---|---|---|---|
| Deterministic commands | 18 | 16 | 2 | 0 |
| deployed predicates | 19 | 18 | 1 | 0 |
| pre_admission predicates | 17 | 15 | 2 | 0 |

| macro | bound | 5 % limit | deployed | pre-admission |
|---|---|---|---|---|
| final_wer | ≤0.095074000 | 0.099827700 | 0.091705333 **strict** | 0.091705333 **strict** |
| immediate_wer | ≤0.166655000 | 0.174987750 | 0.165072333 **strict** | 0.164927167 **strict** |
| settled_wer | ≤0.140442000 | 0.147464100 | 0.135817167 **strict** | 0.135672000 **strict** |
| diarization_error_rate | ≤0.161430000 | 0.169501500 | 0.160881583 **strict** | 0.162669083 **exception** |
| reference_speech_der | ≤0.134804000 | 0.141544200 | 0.133706500 **strict** | 0.135703417 **exception** |
| recall | ≥0.929636000 | 0.883154200 | 0.930811250 **strict** | 0.930956500 **strict** |
| matched_speaker_accuracy | ≥0.911512000 | 0.865936400 | 0.913220583 **strict** | 0.911333250 **exception** |
| time_speaker_attribution | ≥0.876970000 | 0.833121500 | 0.878384667 **strict** | 0.877713167 **strict** |

Failed predicates: `browser_final_summary` (deployed), `browser_final_summary` (pre_admission), `quality_corpus` (pre_admission)

Approved exception set: **DER, reference-speech DER, matched-speaker accuracy**, within 5% relative tolerance, **pre-admission only**; deployed passes all eight strict bounds. QUALITY_BOUNDS and identity policy remain unchanged.

One regression remained (async context protocol in the evidence wrapper, breaking the final-summary probe); fix in progress; round 16 is the confirmation run.

Source: [round-15 report, sanitized copy](../evidence/round-reports/round-15.md). Handoff condition **NOT MET**; terminal **restored**, admitted=false, G7 UNCLAIMED. All 48 main sessions finalized.

## 3. What changed since the 2026-09-10 plan (on the branch; validation scoped by the cited audit)

Use the integrated commit IDs below, not historical sibling-worktree IDs. Each link resolves to the full verified commit SHA. Evidence-only rows do not claim a product fix or a deployed gate pass.

| Area | Change | Commit(s) | Evidence |
|---|---|---|---|
| Terminal prompt | Resolve omitted prompts consistently for live and terminal decoding. | [`2935de6a`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/2935de6a1ee2a9acdba71f55c74a7903d063d46f) | Prompt reproduction and resolution: `/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/8867e7b4-6afc-448e-a8c6-d0a8dbab723a/scratchpad/localstack/NOTES.md` — MacStudio-local (not in repo) |
| Stop | Keep one server-owned drain after caller timeout; return 202 `stop_in_progress`, not session failure. | [`b76b5b5c`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/b76b5b5c420b6963e965d135de701ba6a9fe90ea) | [Stop repair](../audits/resumable-stop-20260911.md) |
| Silent windows | Accept empty output only on speechless PCM (WebRTC voiced fraction <0.01%); speech plus empty still fails. | [`2c285f4e`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/2c285f4e47413dbbf058490b55d401aa34ff513c) | [Classifier evidence](../audits/speechless-terminal-windows-20260911.md) |
| Early text | Publish decoded next-span S00 preview before identity; retire it at the committed audio boundary. | [`578eba55`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/578eba55aabd5d8f96cf3b5a9798d664ffe5923e) | [Preview contract](../audits/canonical-preview-20260911.md) |
| Draft lane | Add optional reader-only drafts and launcher environment wiring; code default remains off. | [`c6acb8b7`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/c6acb8b77dca1324f681c42d85fb51d63409d00a), [`ee52440d`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/ee52440d17bb439f8865cb425715e6472c801112) | [Implementation and original measurements](../audits/draft-lane-20260911.md) |
| Reader cadence | Poll active work every 100 ms instead of 250 ms. | [`eb935313`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/eb935313d907807563681e737c297a41a28af6ff) | [Controlled latency measurement](../audits/browser-latency-budget-20260911.md) |
| LLM relay | Default fresh browser settings to configured key-less models; preserve direct external HTTPS. | [`af164f57`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/af164f574b55119ba05933940e03dd6b1567d6ca) | [Relay diagnosis](../audits/relay-thinking-models-20260911.md) |
| Thinking models | Floor completion budget at 2048, disable thinking, retry reasoning-only once; clarify short-summary prompt. | [`d8ec588c`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/d8ec588c8066085586cb5f215a8f1cc52b89abae) | [Real-model validation](../audits/relay-thinking-models-20260911.md) |
| Naming / exports | Expose speaker controls; propagate acknowledged names; add speaker-labelled SRT/VTT. | [`ab6fdc3d`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/ab6fdc3d7b0621381df78e1e1256eb95cb290622), [`0d831d01`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/0d831d014365fb68460bb6ebbfdfcf90b4327a63), [`c6124fcc`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/c6124fcc6a06af7b97a2ee9a6a3fa5a0a046b61d) | [Naming/export evidence](../audits/rename-export-parity-20260911.md) |
| Workspace UI | Explain capture readiness; selected title/mode; per-item imports; explicit-selection scroll; shell polish; truthful summary actions. | [`24b48395`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/24b48395a6535fc7e25a063e17cecacc67b5faf0), [`937dbd99`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/937dbd997f4823af82514947524c90e731101e9a), [`169a6dfb`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/169a6dfb6b63ebd832d6190cd531fd5d831e1725) | [UI evidence](../audits/workspace-demo-readiness-implementation-20260911.md) |
| Optional enrolment | Default-checked Save voiceprint preserves existing API behavior; unchecked renames only. | [`6b292c40`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/6b292c409ce92ab3cdd0d17a3b1a6ff63ceaba59) | [Checkbox and required lifecycle tests](../audits/round11-browser-regression-20260911.md) |
| Network | Clear stale warnings after recovery; retain real 3 s / 20 s outage scenarios. | [`ad059be5`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/ad059be5e10423854627c7ccccce5b7d6623a0ac) | [Outage evidence](../audits/live-network-resilience-20260911.md) |
| Helper presence | Keep acceptance heartbeats alive during blocking work; browser 45 s background behavior separately measured. | [`83212cea`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/83212ceabe540bdcef69015795fbc5cccc426cde) | [Lease/background evidence](../audits/acceptance-helper-background-settled-20260911.md) |
| Same-tab meetings | Keep native capture focus with a fresh CaptureController per chooser. | [`00ebcd10`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/00ebcd10163670b1b7d48ed40b1ad2777b8f309f) | [Three-cycle real-browser evidence](../audits/same-tab-repeat-capture-20260911.md) |
| Rolling / quality evidence | Recover evicted rolling windows from retained tape; expose content-free identity counts. | [`06a57d2f`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/06a57d2f914c1aadd01e23b1c5ed28641c9fa60e), [`463b1d66`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/463b1d664bee6e9662719613f00afdef0e9f3fd5) | [Recovery evidence](../audits/rolling-eviction-and-der-20260911.md) |
| Terminal diagnostics | Preserve window failure conditions and coordinates. | [`c93395fe`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/c93395fecc2ebf452db66eb4e4ae61afbd855fdb) | [Failure boundaries](../audits/phase2-terminal-failure-20260911.md) |
| Browser predicates | Scope meeting locators; install sentinel titles. | [`f484c635`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/f484c6356e4a556987a6e106692ed4df3654541c) | [Locator/sentinel evidence](../audits/phase2-browser-locators-sentinels-20260911.md) |
| Crash qualification | Read durable transcript_version; wait for actual restart/readiness before continuing. | [`d98f9845`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/d98f98450384890c1fdc0c9f2ca4bfe49e65e5dd), [`83269b7e`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/83269b7e532a60dbf80488821a19a339ebf0f939) | [Repair evidence](../audits/round10-acceptance-repairs-20260911.md) |
| Build/operator qualification | Share embedded identity writer; use actual CLI/journal provenance; await resumable Stop and retain complete capacity ledgers. | [`408e509f`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/408e509facab3a3d50d3f5a3e02f23262bc281f4), [`c07c5d46`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/c07c5d468a24612d0e62f18b1aaddc7fe0eb02d8), [`5c74ddf9`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/5c74ddf9aaad3e1ff744e04bbb237dc9e753f8bc) | [Qualification repair scope](../audits/round10-acceptance-repairs-20260911.md) |
| Portable tests/assets | Keep required API files browser-free; guard optional browser tests; remove checkout-dependent source maps. | [`433e67b2`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/433e67b25274e98eabc4d3523e5256525e7349f7), [`0b3e6a2b`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/0b3e6a2ba72132b90b06758c2f79affece0589c0) | [Required-file audit](../audits/browser-guard-required-files-20260911.md); source-map change verified in linked commit |
| G9 provider paths | Explicit external selection plus fake-upstream relay scenario; share selector between predicate/probe. | [`53d2f0ca`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/53d2f0ca99c8eb0f4b949cf7f6856767d6c186a1), [`76de3e25`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/76de3e25f6de99c047b6eb18e8be02806ed5cd6f) | [Latest probe evidence](../audits/summary-probe-selection-20260911.md) |
| Recognition harness | Derive 4 s label budget and retain decoder timing; do not ship earlier-decode prototype. | [`d6175b46`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/d6175b46d3cef0183750994af772a9c2011a4b24) | [Approved row-10 resolution](../audits/voiceprint-first-match-20260911.md) |
| E2E / operator smoke | Retain 14 browser rows and three same-tab meetings; add isolated row selection and system-trust production smoke. | [`b20dac94`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/b20dac9427f4f3553ce132238f277f94d87cbb61), [`253aaf2c`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/253aaf2c169e3b2824c18f160989352a50923d84) | [Full regression](../audits/same-tab-repeat-capture-20260911.md); [operator smoke](e2e-smoke-for-operator.md) |
| Evidence-only identity work | Measure birth floors with a brief second person; separate mixer-tail/window effects from account carryover. | [`22ef9115`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/22ef9115a71fbd75556297f27cfb03909c1a9996), [`987d17dc`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/987d17dc916edefec7e1216603e9349f2c80b6ef) | [A2](../audits/identity-floor-a2-bench-20260911.md); [path differential](../audits/account-path-der-differential-20260911.md) |
| Mixer repair | Preserve pre-attenuation analysis PCM and release held frame tails; retain six-case measurement and attribution limits. | [`88e226a2`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/88e226a2fdd9457ba1c953c9e062955bbc954bee), [`905eadbb`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/905eadbb39c4ed17a75628bd827edede0ef52b69), [`3d1e2b8a`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/3d1e2b8a2bfb746ffa2a3a1c55040e4b873e7e57), [`3a641f06`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/3a641f06d363d0d4b6dc0ec7d36fe9d4f74bf868) | [Mixer differential](../audits/mixer-repair-differential-20260911.md) |
| Settled text evidence | Measure repaired account/mono text surfaces; the earlier host WER gap predates the accepted mixer repair. | [`1dee922d`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/1dee922dcb203f6d7a9cb7ba1d6016fdb89f9b27) | [Text differential](../audits/text-path-differential-20260911.md) |
| Trailing terminal window | Merge already-covered subsecond tails; accept unparseable output only when the exact PCM is verified speechless. | [`68f7f3ee`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/68f7f3ee67a3a3aa43b4f46ed975ba45f94fb7ab) | [Tail repair](../audits/terminal-short-tail-20260912.md) |
| R11-1 · operator discard projection | Retain queued-item discard events in interrupted public projections. | [`7d82a9e2`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/7d82a9e24cbf70eb6e41513d419aa9bf3b547d34) | [Projection regression](../../tests/phase2/test_owner_bound_live_meeting.py) |
| R11-2 · partial audio seeding | Supply the owning account, session and clip to the deliberate partial-audio fixture. | [`1dab0bb8`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/1dab0bb83575a5e52e6ead4a16edccb3290e20e1) | [Acceptance regression](../../tests/phase2/test_wave1_qualification.py) |
| R11-3 · G9 session ownership | Register owner-b session/helper before seeding its transcript. | [`e03d6a31`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/e03d6a310f86c3db0292ae3de0e784270e01f288) | [G9 diagnosis](../audits/round11-browser-fixes-20260912.md#f2--g9-omitted-owner-registration) |
| R11-4 · hidden observer | Remove Playwright forced focus and throttling bypasses; retain genuine hidden state and post-hidden-only polling checks. | [`e03d6a31`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/e03d6a310f86c3db0292ae3de0e784270e01f288) | [Visibility diagnosis](../audits/round11-browser-fixes-20260912.md#f1--the-page-never-became-hidden) |
| R11-5 · reference bootstrap | Provide the pinned reference health fixture so fidelity preparation boots. | [`5993afcb`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/5993afcb29c55bda1c2e22107b8766378f49852d) | [Reference regression](../../tests/phase2/test_browser_timeout_evidence.py) |
| R11-6 · relay attempt synchronization | Wait for current state of the new POST’s exact attempt ID, not a restored older summary. | [`e03d6a31`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/e03d6a310f86c3db0292ae3de0e784270e01f288) | [Relay race](../audits/round11-browser-fixes-20260912.md#f3--old-summary-satisfied-the-relay-completion-wait) |
| Earlier staging / G8 fixes | Finalize and verify staged provider identity; register G8 sessions through the owning helper. | [`9dc047f8`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/9dc047f8dd5d05fd63bc4ca908d1bcdc9f440372), [`15b35860`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/15b35860e674ad38cf1af750552c6a347ab9be38) | [Staging tests](../../tests/test_live_manifest_finalizer.py); [helper tests](../../tests/phase2/test_acceptance_helper_lifetime.py) |
| Earlier cleanup / audio fixes | Close observers; recognize recovered terminal cleanup; compare archives with mixed PCM; create a deliberate partial-audio case. | [`62a3c601`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/62a3c60142491e106984430f813ff0f85d31b498), [`2b709b2f`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/2b709b2f3a668baba6c53cc8c486fa538d6ffca5), [`70f1480d`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/70f1480de9ed811ca70037a4e5cb5da25093137f) | [Cleanup tests](../../tests/phase2/test_acceptance_cleanup.py); [audio tests](../../tests/phase2/test_wave1_qualification.py) |
| Earlier operator / overload setup | Burst canonical work before interrupt; drive eight-session input beyond declared lane capacity. | [`809a9a5e`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/809a9a5e9b656fd19b7228ea3dfaf57b0665ce68), [`c70a96e2`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/c70a96e22be4108c5f4f760fe4dd493a38ea0a21) | [Overload test](../../tests/phase2/test_acceptance_overload_window.py) |
| Browser failure evidence | Retain bounded diagnostics and strengthen readiness; subsequent content-boundary cleanup narrows retained fields. | [`cf0dc398`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/cf0dc39812dd699e40d2ac1ee718c0cfd47fc315) | [Timeout audit](../audits/browser-timeout-evidence-20260911.md); [current boundary](../audits/content-boundary-20260912.md) |
| Browser availability | Prove optional G9 cases skip before probe setup when the executable is missing. | [`f8e66aeb`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/f8e66aeb552cb8691759ff405de324ffa692acb9) | [Guard audit](../audits/summary-browser-guard-20260911.md) |
| E2E sequencing | Diagnose pre-existing 13→14 Reset timing; require durable completion and terminal UI before Reset, with a bounded wait. | [`5c226b43`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/5c226b4366ae8c42fa8b237d461d979924ada965), [`b1feae6f`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/b1feae6fe99f492dc95e62df597fae3081a8698b) | [Diagnosis](../audits/mixer-e2e-regression-20260911.md); [combined 13/14 rerun](../audits/e2e-reset-sequencing-20260911.md) |
| Operator precheck / handback | Add trusted-TLS, exact-SHA and timed model precheck; assemble evidence handback and qualified limitation wording. | [`7fd9f4d0`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/7fd9f4d0789143258c5d431c5309e2ad8d523114), [`8a2dc33a`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/8a2dc33a23f07b57e20d29a5f7bd209bf839a825), [`8f274786`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/8f274786a46927323fb606ce31414fbcb39b3216) | [Precheck audit](../audits/demo-precheck-20260911.md); this handback |
| Content boundary | Remove retained content/caches and prevent diagnostic writers from recreating them; product relay error paths verified clean. | [`09539ad7`](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/commit/09539ad72006d756fcece932efe74fbb6d8490b1) | [Boundary audit and inventory](../audits/content-boundary-20260912.md) |

### Earlier measured quality — round 11; provisional round 12 is in section 2

Use **round 11 (`c70a96e2`, draft lane ON)** as the latest measured host result; **round 12 is in flight**. All eight quality macros fall inside the approved band in both layers, and four-session capacity passes both layers. S = strict bound; E = pre-approved 5% exception. Bounds and identity policy remain unchanged. Source: [issue #10, round-11 result](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/10#issuecomment-5643836080).

| macro | bound | deployed | pre-admission |
|---|---|---|---|
| final WER | ≤ .095074 | **.0917 S** | **.0917 S** |
| immediate WER | ≤ .166655 | **.1648 S** | **.1660 S** |
| settled WER | ≤ .140442 | **.1355 S** | **.1357 S** |
| recall | ≥ .929636 | **.9313 S** | **.9310 S** |
| time-speaker attribution | ≥ .876970 | **.8778 S** | **.8779 S** |
| matched-speaker accuracy | ≥ .911512 | **.9116 S** | .9113 E |
| diarization error rate | ≤ .161430 | .1626 E | .1624 E |
| reference-speech DER | ≤ .134804 | .1357 E | .1354 E |

This is not an all-gates pass: round 11 retained six browser/operator/audio/probe items and **2/8 overload finalization failures per layer** on a redundant 0.5 s terminal tail; the repairs above await round-12 measurement. Do not replace section 2’s `<ROUND>`, `<SHA>` or `<TABLE>` until the operator has the final result.

## 4. Verified feature checklist (14 rows)

Use the [same-tab audit](../audits/same-tab-repeat-capture-20260911.md) (raw candidate artifacts removed under the content boundary): **14/14 PASS at `00ebcd10`**, real local Chromium/decoder, draft lane 1.0, separate state and relay configured. This is not a new run at the handback SHA, not the MacBook’s actual AirPods capture, and not deployed qualification. The [original audit](../audits/e2e-feature-verification-20260911.md) remains 10/12 historically; row 9 and row 10 were subsequently resolved. The [13-row audit](../audits/round11-browser-regression-20260911.md) bridges those runs; its unresolved repeat-capture note is superseded by row 14.

| Row | Verified behavior | Result / checked artefact |
|---:|---|---|
| 1 | Fresh workspace | [PASS — Signed in; workspace boot ready.](../audits/same-tab-repeat-capture-20260911.md) |
| 2 | MP3 upload | [PASS — Completed; 10 edits / 115 reference words = 8.70% WER.](../audits/same-tab-repeat-capture-20260911.md) |
| 3 | Media URL | [PASS — Completed; same 8.70% WER, local reachable URL fixture.](../audits/same-tab-repeat-capture-20260911.md) |
| 4 | Live microphone + tab | [PASS — Both meters; first visible text 2.335 s; Stop to completed 2.053 s.](../audits/same-tab-repeat-capture-20260911.md) |
| 5 | Rename both controls | [PASS — Transcript-row label and legend; acknowledged names in history and export.](../audits/same-tab-repeat-capture-20260911.md) |
| 6 | Transcript exports | [PASS — MD/TXT/JSON/SRT/VTT downloaded; nonempty, cues/timing/speaker prefixes checked.](../audits/same-tab-repeat-capture-20260911.md) |
| 7 | Completed audio | [PASS — 50.0 s MP3 downloaded and decoded.](../audits/same-tab-repeat-capture-20260911.md) |
| 8 | Interrupted audio | [PASS — Interrupted meeting; 11.42 s partial MP3 decoded.](../audits/same-tab-repeat-capture-20260911.md) |
| 9 | Relay summaries | [PASS — Both configured models returned current, rendered, validated summaries.](../audits/same-tab-repeat-capture-20260911.md) |
| 10 | Enrolled recognition | [PASS — Visible saved name 3.6897 s after Start; bound 4.0 s; decoder trace retained.](../audits/same-tab-repeat-capture-20260911.md) |
| 11 | History → transcript | [PASS — Selected title/mode correct and header visible.](../audits/same-tab-repeat-capture-20260911.md) |
| 12 | Phone-width layout | [PASS — 400 px viewport and scroll width; navigation anchors visible.](../audits/same-tab-repeat-capture-20260911.md) |
| 13 | Network resilience | [PASS — 3 s and 20 s origin outages; sequences preserved; both completed/final.](../audits/same-tab-repeat-capture-20260911.md) |
| 14 | Consecutive same-tab meetings | [PASS — Three distinct meetings, same document; all completed/final and in history; pane/export bound to each new meeting.](../audits/same-tab-repeat-capture-20260911.md) |

The [row-14 audit](../audits/same-tab-repeat-capture-20260911.md) records the historical reset proof: the pane cleared before each Start. The default-checked **Save voiceprint** change has checked/unchecked API/UI tests and **61 required lifecycle tests, no skips** in the [13-row audit](../audits/round11-browser-regression-20260911.md).

## 5. Latency (measured; keep the clocks separate)

Use these as local observations, not an end-to-end service-level promise. “Coverage” measures when text covers audio buckets; it is not first-word latency. Do not subtract different runs/clocks to invent browser overhead.

| Measurement | Verified number | Source and boundary |
|---|---|---|
| Early API baseline, `c6124fcc`, 50 s corpus | First text **2.34 s**; coverage p50 **2.29 s**; label p50 **2.49 s**; finalization final | Original local-stack NOTES: `/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/8867e7b4-6afc-448e-a8c6-d0a8dbab723a/scratchpad/localstack/NOTES.md` — MacStudio-local (not in repo). Historical probe clock subtracts the first emitted segment start; not independently measured physical onset. |
| Single session, lane off → on | Coverage p50 **1.80 → 0.77 s**; p95 **2.94 → 2.32 s**; first text from stream start **3.750 → 2.392 s** | [Draft-lane audit](../audits/draft-lane-20260911.md), successful paired arms; 69 steady buckets per session. |
| Two sessions, successful off → on repeat | Coverage p50 **2.23/2.16 → 1.30/1.72 s**; p95 **3.36/3.40 → 3.17/3.36 s** | Same audit: separate per-session percentiles, not pooled. Earlier concurrent-on arm failed; retain it, do not average it away. |
| Controlled ready-to-browser-text delay | Median **128.4 → 82.8 ms**, improvement **45.6 ms**; JSON-to-DOM **0.8–0.9 ms** | [Browser latency budget](../audits/browser-latency-budget-20260911.md): seven readiness phases, polling 250 → 100 ms, no decoder. |
| Known-waveform onset to matching browser speech | About **3.29 → 3.28 s**, no material end-to-end gain | Same audit: draft off; waveform-aligned browser fixture, not physical AirPods latency. Earlier ~945 → 699 ms first-text observations were non-speech and rejected. |
| First enrolled label | Approved corrected baseline **3.7007 s**; later full run **3.6897 s**, both ≤4.0 s | [First-match audit](../audits/voiceprint-first-match-20260911.md): Start click to DOM mutation; bound = 2.5 s span cap + ~1.0 s decode/identity + 0.5 s frame/poll allowance. |

The original **10.8447 s** label observation remains a failure. Its first runner call took **7.0683 s**; bank matching already occurred in the first publication, approximately 10 ms after identity commit in the traced run. No sweep-trigger delay was found. The operator attributed the stall to shared-tunnel contention; the trace itself cannot separate conversion, transport and upstream time. Do not claim a fixed “+0.2 s for known names” from the aggregate label/text medians. [Recognition trace and limits](../audits/voiceprint-first-match-20260911.md).

Treat the original NOTES “WER 0.0708” as its old matching-block heuristic, not true word error rate. The [draft audit](../audits/draft-lane-20260911.md) corrects the metric: all six successful draft-study arms had full Levenshtein WER **0.0885**. This differs from the separate browser upload fixture’s 10/115 WER and is not a contradiction.

For concurrency context, the retained [headroom report](../evidence/round-reports/draft-headroom-20260911.md) at `5c74ddf9` measured four-session pooled canonical p95 **13.66 s off / 13.69 s on**, worst-session **16.09 / 18.50 s**, and all sessions final. Four-on skipped **197/200** draft ticks. Eight-on finalized **8/8**, coverage p50 **17.86–21.91 s**, p95 **59.82–65.71 s**; all eight first returned `stop_in_progress`, with no helper-lease expiry. Sampled KV-cache peaks were **5.47% / 5.35% / 5.47%** (four-off/four-on/eight-on); running requests peaked at two, waiting at six under eight. The report is in the repository; its raw scratch sources remain MacStudio-local (not in repo). They do not certify the host capacity gate.

## 6. Decisions you may want to revisit later

- **D1 — Keep identity thresholds unchanged:** birth **1.0 s**, album admission **2.0 s**, causal match score **0.35**, margin **0.10**. Keep private-bank matching distinct from album admission. Do not infer that a microphone contains only one person or add channel-specific floors. The [A2 bench](../audits/identity-floor-a2-bench-20260911.md) reused identical observations: floor 1 s had one false split but missed no person; floors 1.5/2 s left both people unnamed for 40 s in the all-short scenario. With a stable main speaker, raising the floor still lost the genuine 1 s guest. A later 2 s return allowed correction only after **50.6 audio-seconds**. Nine-clip default accuracy mean/min **93.97%/84.70%**; Jamie Dimon at floor 2 s **49.44%**, reproducing ADR-0002’s cold-start failure. This is a bench result, not every conversation.
- **D2 — Separate words from names.** The [peer handoff](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-mic-latency-review-20260911/docs/handoffs/mic-latency-diagnosis-prototypes-20260911.md), committed separately at `92a4d4b899c2fd40896f35c0dc9050c2c117474c`, found 39 one-second observations → 2 identities at floor 1 s, **zero** at floor 2 s, with all text markers preserved. Its preview follow-up is now implemented; its A2 request is now measured. The actual MacBook AirPods failure remains device-specifically unconfirmed; short evidence is established, a Bluetooth bug is not. Virtual Desktop devices were not used. This peer source lives outside the deliverable branch.
- **D3 — Retain lane ON for the demo candidate by the operator’s later decision:** `MOSS_LIVE_DRAFT_LANE_SECONDS=1.0`; code default remains OFF. This explicitly supersedes the earlier OFF recommendations in the draft/headroom reports. The strict four-session non-regression criterion was mixed, not proven; the operator accepted the noisy comparison and graceful completion for demo use. Do not turn that decision into a fabricated gate pass. Fill actual gates in section 2.
- **D4 — Preserve QUALITY_BOUNDS and the scored surfaces.** [Retained round-9 analysis](../audits/round9-quality-retained-20260911.md) shows “immediate” already included rolling revisions in 11/12 sessions; the immediate-to-settled increase came from canonical tail commits, not new rolling revisions or Stop. Javier’s evicted rolling window motivated the separate tape-recovery fix. [Account-path differential](../audits/account-path-der-differential-20260911.md) isolates held mixer tail and attenuation-induced endpoint/embedding changes, including a real third provisional identity; it rejects account carryover for the measured empty-bank path, not every workflow. Do not equate fewer visible speakers with better quality.
- **D5 — Defer earlier-first-decode scheduling to a later task.** Permission was granted for later work only; no earlier-decode prototype shipped here. Preserve current capture/identity contracts during this handback.

## Known limitations and how to talk about them

1. **Settled word error rate (WER):** the historical gap is superseded by round 11: **13.55% deployed / 13.57% pre-admission**, both below the **14.0442%** bound; the earlier .1693 host score predates the mixer repair, so do not present runtime non-reproducibility as the established cause. [Latest host table](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/10#issuecomment-5643836080), [text-path audit](../audits/text-path-differential-20260911.md).
2. **New voices:** ask for **~2 s of contiguous speech** for stable identity evidence; short fragments may remain unlabeled by design, while the **1.0 s birth floor / 2.0 s album admission** mean “no label before 2 s” is not an absolute rule or a wall-clock guarantee. [Identity-floor bench](../audits/identity-floor-a2-bench-20260911.md).
3. **Concurrency:** plan for **4 supported sessions**, not 8; the local eight-session overload run reached **8/8 closed/final**, but coverage latency p50 rose to **17.86–21.91 s** (~20 s), with p95 **59.82–65.71 s**—graceful completion, not a host capacity certificate. [Today's retained headroom measurement](../evidence/round-reports/draft-headroom-20260911.md).
4. **G7 canary:** arrange a working **host display and microphone/audio path**; the runbook recorded **WSLg 1.0.66 disabled (`guiApplications=false`)**, so SSH alone is insufficient—have the operator verify readiness before booking the attended attempt. [G7 runbook](g7-preadmission-runbook.md#choose-a-display-before-booking-the-attempt).
5. **Relay scope:** describe the demo relay as the **2 configured key-less tailnet models** (MacStudio primary, RTX4090 fallback); external HTTPS providers remain browser-owned, not arbitrary server-proxied endpoints. [Provider-path audit](../audits/g9-provider-paths-20260911.md), [recorded relay configuration](../llm-relay.md).
6. **Thinking-model delay:** say “RTX4090 fallback can spend time reasoning”; the old **1,024-token** request took **20.41 s** with no answer versus **11.76 s** when thinking alone was disabled; the relay now disables thinking and permits **1 bounded retry**, so these are diagnostic observations, not current latency promises. [Thinking-model audit](../audits/relay-thinking-models-20260911.md).
7. **Long silence:** an empty **150 s** terminal window succeeds only when WebRTC voice activity detection finds **<0.01% voiced PCM samples**; empty output with speech still fails, and silence is classified after decoding rather than skipped for speed. [Speechless-window audit](../audits/speechless-terminal-windows-20260911.md).
8. **Draft lane under load:** describe it as designed to yield to canonical work; four-session backoff skipped **197/200 ticks (98.5%)**, with pooled canonical p95 **13.66 s off / 13.69 s on**—operator-accepted practical neutrality, not proven strict non-regression or guaranteed GPU priority. [Headroom measurement](../evidence/round-reports/draft-headroom-20260911.md), [draft scheduling limits](../audits/draft-lane-20260911.md).
9. **Host disk hygiene:** round 13 filled C: with a **570 GB** WSL `ext4.vhdx`, taking Phase-1 down. Linux deletion does not automatically shrink that disk. Guards now require **20 GB WSL-root / 10 GB C:** free; export evidence bundles before retention pruning (`python3 moss_transcribe_diarize/candidate_storage.py --dry-run`, then `--prune`). Windows reclamation or relocation requires planned downtime: temporarily disable **both `MinerU-WSL-Keepalive` and `MinerU-Windows-Watchdog`**, which can restart Ubuntu (and WslService) within **~20 seconds** of shutdown; re-enable both afterward; **never shut down WSL during an attempt**. vLLM returns with a new PID and Phase-1 needs recovery/readiness checks. Follow [Host disk hygiene](g7-preadmission-runbook.md#host-disk-hygiene), including the verified recovery facts above and durable canonical-host prerequisite.
10. **Shared GPU:** MinerU's container engine and vLLM share the Alienware's **RTX 4070 Ti SUPER**. At **04:58 EDT on 2026-09-12**, combined use was **13,658 of 16,376 MiB**; vLLM is pinned to `--gpu-memory-utilization 0.30` (about **4.9 GB**). Load gates were measured under this contention. Recommend pausing MinerU for client demos when latency matters; this is the operator's decision, and nothing was changed.

## 7. Rollback

Follow [G7 recovery](g7-preadmission-runbook.md#7-recover-an-interrupted-attempt-only). If an attempt has **no terminal journal phase**, first have the engineer confirm the original cutover process has stopped, then use the matching installed CLI:

```sh
mtd-phase2-cutover restore --attempt <ATTEMPT>
```

Do not add `--profile`. Restore uses the attempt’s stored state and **refuses terminal attempts**, including successful preadmission and already-restored failures. `SAFE_STOPPED` requires the engineer. Arrange later rollback of a successfully serving candidate separately; this runbook does not establish a “new cutover of the previous candidate” recipe.

## Evidence index — today’s branch audits and handoffs

- [Portable reports and local-source disposition](../evidence/round-reports/README.md) — Reviewed report copies, with unavailable or rejected sources explicitly identified.

Read these as dated evidence with their stated scope, not interchangeable gate certificates. Inventory includes the September-11 work and subsequent September-12 updates through the reviewed head. Content-removal notices supersede older raw-artifact retention claims. The peer handoff and original scratch latency notes are linked above separately because they are not branch files.

- [acceptance-helper-background-settled-20260911](../audits/acceptance-helper-background-settled-20260911.md) — Acceptance heartbeat repair and genuine 45 s hidden-tab capture; its missing quality evidence is resolved by the later round-9 audit.
- [account-path-der-differential-20260911](../audits/account-path-der-differential-20260911.md) — Mixer tail and attenuation change coverage/embedding windows; measured empty-bank account carryover is rejected.
- [auto-mvp-browser-test-portability-20260911](../audits/auto-mvp-browser-test-portability-20260911.md) — Original missing-Chrome locator guard; later shared required-file audit supersedes its remaining browser concerns.
- [browser-guard-required-files-20260911](../audits/browser-guard-required-files-20260911.md) — All 24 required files ran browser-forbidden: 393 passes, zero skips; optional browser paths share honest guards.
- [browser-latency-budget-20260911](../audits/browser-latency-budget-20260911.md) — 100 ms polling saves measured reader wait, not the claimed large end-to-end delay; non-speech timing rejected.
- [canonical-preview-20260911](../audits/canonical-preview-20260911.md) — Locked next-span text preview precedes identity and retires correctly on commit/abort.
- [draft-lane-20260911](../audits/draft-lane-20260911.md) — One/two-session draft results, failed arm and lifecycle tests; original OFF recommendation superseded by operator decision.
- [e2e-feature-verification-20260911](../audits/e2e-feature-verification-20260911.md) — Original 10/12 real-browser baseline; failed summaries and delayed recognition preserved.
- [g9-provider-paths-20260911](../audits/g9-provider-paths-20260911.md) — Explicit external selection and a separate real browser-to-relay fake-upstream G9 scenario.
- [identity-floor-a2-bench-20260911](../audits/identity-floor-a2-bench-20260911.md) — Identical-observation floor comparisons expose missed brief people and reproduce the nine-clip cold-start regression.
- [live-network-resilience-20260911](../audits/live-network-resilience-20260911.md) — Real 3 s/20 s outages recover; product fix clears a stale warning.
- [phase2-browser-locators-sentinels-20260911](../audits/phase2-browser-locators-sentinels-20260911.md) — Mounted/fallback meeting-card ambiguity fixed with scoped locators; audio sentinel titles installed.
- [phase2-crash-prefix-20260911](../audits/phase2-crash-prefix-20260911.md) — Crash probe read transcript.version instead of durable top-level transcript_version.
- [phase2-fragment-embedding-measurement-20260911](../audits/phase2-fragment-embedding-measurement-20260911.md) — Fresh local short-fragment embeddings reproduce low similarity even after voiced-only filtering.
- [phase2-fragmented-speech-identity-20260911](../audits/phase2-fragmented-speech-identity-20260911.md) — Code trace distinguishes birth from album admission; silence itself does not reset identity.
- [phase2-pre-stop-termination-20260911](../audits/phase2-pre-stop-termination-20260911.md) — A terminal 409 does not establish its cause; cached-session/helper lifetime investigated without automatic restart.
- [phase2-round7-preflight-20260911](../audits/phase2-round7-preflight-20260911.md) — Historical regression-risk review; explicitly not a forecast of gate success.
- [phase2-terminal-failure-20260911](../audits/phase2-terminal-failure-20260911.md) — Separates capture completion from failed finalization and enumerates diagnostic failure paths.
- [relay-thinking-models-20260911](../audits/relay-thinking-models-20260911.md) — Exact-prompt upstream replay identifies reasoning exhaustion and empty inner summaries; verifies bounded fix.
- [rename-export-parity-20260911](../audits/rename-export-parity-20260911.md) — Acknowledged naming across surfaces and SRT/VTT correctness; deferred checkbox note superseded by round11 audit.
- [resumable-stop-20260911](../audits/resumable-stop-20260911.md) — Caller deadline no longer kills server-owned drain; API/UI pending semantics tested.
- [rolling-eviction-and-der-20260911](../audits/rolling-eviction-and-der-20260911.md) — Recovers queued rolling PCM from the retained tape; no unmeasured deployed quality gain claimed.
- [round10-acceptance-repairs-20260911](../audits/round10-acceptance-repairs-20260911.md) — Crash readiness, canonical build identity, operator oracles and capacity event collection repaired; no qualification claim.
- [round11-browser-regression-20260911](../audits/round11-browser-regression-20260911.md) — Default-checked enrolment option and 13 passing browser rows; repeated-page limitation later resolved.
- [round9-quality-retained-20260911](../audits/round9-quality-retained-20260911.md) — All twelve retained quality cases show canonical-tail causes of settled change and one rolling eviction.
- [row10-recognition-readonly-20260912](../audits/row10-recognition-readonly-20260912.md) — Original 10.8447 s recognition trace locates delay inside the first decoder runner call.
- [same-tab-repeat-capture-20260911](../audits/same-tab-repeat-capture-20260911.md) — Native macOS capture-focus rejection fixed; 14/14 full run and three same-document meetings retained.
- [speechless-terminal-windows-20260911](../audits/speechless-terminal-windows-20260911.md) — Strict VAD classification accepts empty silent windows while speech-empty still fails.
- [summary-probe-selection-20260911](../audits/summary-probe-selection-20260911.md) — Shared sync/async provider selector; baseline and patch pass locally, reported host failure remains unconfirmed.
- [voiceprint-first-match-20260911](../audits/voiceprint-first-match-20260911.md) — Bank matching is immediate at publication; derived 4 s criterion passes without policy/geometry change.
- [workspace-demo-readiness-implementation-20260911](../audits/workspace-demo-readiness-implementation-20260911.md) — Capture readiness, selected context, per-item import outcomes, explicit scroll and summary-action UI evidence.

- [G7 preadmission runbook](g7-preadmission-runbook.md) — Display/audio prerequisites, attended procedure and interrupted-attempt recovery; preadmission is not admission.
- [Operator E2E smoke](e2e-smoke-for-operator.md) — Exact production-origin commands, row prerequisites, fresh-workspace isolation and 4/4 no-decoder local evidence.
- [Presenter demo script](demo-script.md) — Ten-minute client flow with exact controls, expectations and recoveries.

- [browser-timeout-evidence-20260911](../audits/browser-timeout-evidence-20260911.md) — Original timeout/readiness instrumentation; current retained fields are narrowed by the content-boundary audit.
- [content-boundary-20260912](../audits/content-boundary-20260912.md) — 402 evidence files and 16 caches removed; metadata-only writers enforced and production relay error paths verified clean.
- [demo-precheck-20260911](../audits/demo-precheck-20260911.md) — Trusted TLS, full candidate SHA, configured models and sequential 16-token health probes; local failure paths verified.
- [e2e-reset-sequencing-20260911](../audits/e2e-reset-sequencing-20260911.md) — Bounded durable/UI terminal wait repairs the combined 13→14 handoff; targeted 2/2 rerun, not a new full 14-row run.
- [mixer-e2e-regression-20260911](../audits/mixer-e2e-regression-20260911.md) — Nine requested rows pass; row-14 combined failure reproduces before mixer repair and is isolated to Reset sequencing.
- [mixer-repair-differential-20260911](../audits/mixer-repair-differential-20260911.md) — Six-case repair measurements and source-analysis versus observed-end attribution; per-case tradeoffs retained.
- [mixer-repair-feasibility-20260911](../audits/mixer-repair-feasibility-20260911.md) — Rejected shortcuts and measured corrected mixer design before implementation.
- [round11-browser-fixes-20260912](../audits/round11-browser-fixes-20260912.md) — Forced-focus, unregistered G9 session and stale-summary attempt races repaired; local checks do not replace host qualification.
- [summary-browser-guard-20260911](../audits/summary-browser-guard-20260911.md) — Optional G9 entrypoints skip with a missing-executable reason before probe setup.
- [terminal-short-tail-20260912](../audits/terminal-short-tail-20260912.md) — Redundant subsecond terminal windows reproduced; merged coverage and verified-silence classification repaired.
- [text-path-differential-20260911](../audits/text-path-differential-20260911.md) — Repaired account settled WER .136379 versus mono .137097; earlier host score measured pre-repair.

### Draft corrections to retain

- Removed the unverified PR URL/unmerged status and “Issue #10 has every round”; no branch PR was found, and complete round coverage was not established.
- Replaced fixed 60–75 minute preadmission timing with the runbook’s hour-or-more estimate; removed unconditional “any failure auto-restores” and any implication that preadmission means admitted.
- Removed guaranteed enrolment after ≥3 s, “≈0.95 s browser overhead”, and fixed “+0.2 s known-name delay”; their cited evidence does not establish those claims.
- Replaced the old preview/summary sibling SHAs with integrated branch ancestors and the polling documentation SHA with its implementation SHA. Removed the blanket “all tested” qualification implication; each row carries its own audit scope.
- Replaced generic “2 s removes all identities” with the exact controlled short-observation case; corrected historical heuristic WER and first-text clock semantics.
- Replaced upstream server software-brand assertions with the verified URL/model configuration; branch audits verify responses, not the currently running server packages.
- Removed the unsupported successful-preadmission rollback recipe. Keep the documented interrupted-attempt restore boundary and arrange later rollback with the engineer.

No product code, live service, host configuration, database or gate result was changed to assemble this document.
