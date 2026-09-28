# Round-6 UI sync watch

Checked 2026-09-28 00:39 EDT against `$WT` `gemini/live-hybrid` at `7fce0f3d` (base `8d8fb682`). Read-only source inspection. No UI change was copied into the Gemini branch; lead decides the merge.

| Source | Head / UI commit | Frontend files since `8d8fb682` | Backend/static dependency | In integration `8d8fb682`? | Clean on Gemini WT? |
| --- | --- | --- | --- | --- | --- |
| `/Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate` (`round6/integration`) | `8d8fb682` | none | none | yes, it is the base | yes, empty diff |
| `/private/tmp/moss-round6-impl-ui-u1u2` (`round6/impl-ui-u1u2`) | `a9301117` D53 inline passage action and summary page | `frontend/src/components/{MeetingHistory.test.tsx,MeetingHistory.tsx,TranscriptPane.tsx,speakerRename.test.tsx}`, `frontend/src/state/ui.ts`, `frontend/src/styles/index.css` | `moss_transcribe_diarize/phase2_acceptance_summary.py`; rebuilt `app/frontend_assets/{app.js,app.js.map,styles.css}`; related acceptance tests and demo script. Dirty CSS/layout refinement plus `phase2_acceptance_summary.py`, static CSS and locator test; one untracked screenshot fixture. | no | yes: committed diff `8d8fb682..a9301117` passed `git apply --check` on a temporary worktree at `7fce0f3d`; dirty tracked diff also passed after applying committed patch there. Untracked fixture was not tested. |
| `/private/tmp/moss-dxc-lead` (`dx/combined`) | original path pruned; active branch recovered at `/private/tmp/moss-dxc-integ`, head `032cb1ce` | `frontend/src/api/{mossPoller.ts,mossPoller.test.ts,types.ts}`, `components/{DxQ5Rows.tsx,TranscriptPane.tsx}`, `lib/{dxQ5.ts,dxQ5.test.ts,mergeTranscript.ts,mergeTranscript.test.ts}`, `state/session.ts`, `styles/index.css` | Live D55 preset, lane gate, progressive settlement and runtime/session plumbing in `moss_transcribe_diarize/app/`; rebuilt `app/frontend_assets/{app.js,app.js.map,styles.css}`. | no | yes: full committed diff `8d8fb682..032cb1ce` passed `git apply --check` in a temporary worktree at `7fce0f3d`. |
| `/private/tmp/moss-dx-replay` (`dx/replay`) | `27334d4c`; Q5 prototype in `23a41abe` | none | Q5 lives in `prototypes/round6-replay/q5_prototype.py`, no product frontend/backend diff since base | no, prototype branch only | yes, empty product diff |

**Apply-check method:** Detached temporary worktrees at `7fce0f3d`. D53: `git apply --check` on the committed patch, then apply it only inside the temporary worktree and `git apply --check` on the dirty tracked patch. D55/Q5: `git apply --check` on the entire committed `dx/combined` diff. Temporary worktrees were removed. These checks establish textual applicability for each branch separately; combined compatibility, runtime behavior, and UI adoption are unmeasured.

**Next watch:** recheck around 01:39 EDT if this pane remains active. The original `moss-dxc-lead` path remains absent, but the `dx/combined` branch is available in `moss-dxc-integ`.

**00:44 EDT recheck:** Heads unchanged: integration `8d8fb682`, D53 `a9301117`, combined `032cb1ce`, replay `27334d4c`. No new UI delta was detected during this pane's run. This pane closes before the 01:39 scheduled watch; the lead may continue the hourly watch.

**00:47 EDT worktree update:** Gemini head advanced to `bc567bb2` for `common/gemini_common.py` word-offset repair. `frontend/` has no diff from `7fce0f3d`; the D53 and D55 source patches do not touch `common/gemini_common.py`. The temporary-worktree apply checks above were made against `7fce0f3d`; no conflicting path appeared in the new commit.
