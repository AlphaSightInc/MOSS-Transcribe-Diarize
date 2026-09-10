# Browser-workspace prototype verdict — September 10

Question: can automatic browser bootstrap reuse the production owner-bound Meeting store while preserving cross-tab continuity, cross-profile isolation, and ordinary restart persistence?

Command: `PYTHONPATH=. python prototypes/phase2-account-lifecycle/browser_workspace_probe.py` from the implementation worktree using its dependency environment.

Measured on macOS, real headless Chrome with `--mute-audio`, loopback secure context, SQLite **3.50.4**. This is semantic/browser evidence, not pinned Linux SQLite 3.53.4 or production-TLS qualification. No microphone, screen, media playback, or volume control was used. Scratch databases/profiles were cleaned after each run.

## Result: 11/11 observations match the contract

- Two concurrent tabs share one workspace under a same-origin Web Lock.
- Another browser profile has a different workspace.
- Foreign meeting lookup returns 404.
- JavaScript cannot read the cookie; observed flags Secure, HttpOnly, SameSite=Lax.
- Proposed schema removes the Google allowlist/owner-email header while reusing production meeting/child tables and operations.
- Browser and actual server restart preserve workspace identity.
- Saved meeting remains in history after those restarts.
- Lost-cookie creation returns 401, without silently bootstrapping another owner.
- A fresh explicit bootstrap after cookie deletion creates a separate workspace.
- An invalid existing credential causes bootstrap to return 401.
- **Falsifier observed:** with the lock removed and cookie delivery delayed 50 ms, two first tabs returned **two distinct workspace identities**, versus one with the lock. The delay is experiment instrumentation, not a product timeout/threshold.

Verdict: use a browser-wide Web Lock around session check → optional bootstrap → cookie round-trip verification before admitting UI work. Keep credentials HttpOnly, not in localStorage. Fail visibly if locks/cookies are unavailable; do not add a second fallback identity policy. Use a new explicit schema version and retain existing owner-bound Meeting handles. Absorb these primitives into production, then rerun through the installed application; this throwaway header substitution is not production code.

Read-only host inventory: both configured candidate database `/home/devcontainers/.local/share/moss-transcribe-diarize/account/moss-phase2.sqlite3` and default `/home/devcontainers/.local/share/moss-transcribe-diarize/phase2.sqlite3` were absent. No existing candidate user history was found at those paths; no database or archive was deleted.
# Production-path absorption — 2026-09-10

The browser bench now runs `create_phase2_app` and its shipped bootstrap JavaScript,
not a proposed store subclass or duplicate HTTP handlers. All 11 original checks pass
on Python 3.12.12 / host SQLite 3.50.4, headless muted Chrome. The no-lock control
modifies the actual served script; a 50 ms injected cookie delay still produces two
owners without the lock. The lock produces one. No microphone or playback API runs.

Separate desktop/mobile UI fixtures share a test cookie to represent views of one
workspace; this does not implement browser linking. Separate-profile isolation is
measured here. Active audio is not declared unavailable before finalization; the UI
regression uses a terminal unavailable-audio fixture to test that label.

These are semantic/browser checks, not pinned Linux, trusted TLS, inference quality,
load, or attended capture qualification. Historical Google-policy probes below this
directory are superseded where ADR-0013 changes their premise.
