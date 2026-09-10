# Speaker display state — 2026-09-10

Question: can naming update a silent Live view without treating names as identity
or resetting its speech cursor? Minimum state: canonical ID identifies the speaker;
label displays the name; speech and label revisions describe independent changes.
Assumption: label revisions are monotonic within a Live binding, not across meetings.
Falsifiers: two Alexes merge, naming waits for speech, unchanged replies redraw forever,
or history loses the canonical ID. Use a state probe first; then the actual poller,
UI and owner-bound HTTP/store tests to reject those outcomes. No new audio algorithm.

The throwaway four-event Node probe printed full state: initial speech version 7,
two distinct canonical speakers; label revision 1 named both Alex; repeated revision
1 caused no render; revision 2 removed one label. Observed: speech version stayed 7,
two identities stayed distinct, three renders, removed label restored S02. All four
checks passed. The probe was absorbed into the production poller and its regression
test; standalone simulation deleted.

Production decision: cache canonical rendered rows, overlay display names on full
snapshots and label-only revisions, and retain the independent speech cursor. No new
speaker event or forced full-snapshot loop. Persist canonical IDs alongside display
labels in Live transcript JSON so saved duplicate names cannot merge in history.
File transcripts without Live identities retain their existing speaker keys.

Regression command:

```sh
npm --prefix frontend test
.venv/bin/python -m pytest -q tests/phase2/test_owner_bound_live_meeting.py --tb=short
```

Real muted/headless Chrome visual/interaction check used the actual Vite components
with explicitly synthetic session state and a mocked naming response. Two Alex chips
opened the selected speaker's modal; Save issued one PUT for canonical-b only and
rendered Alex/Sam as two turns; pending enrollment explanation appeared; clearing
page-local capture ownership disabled both chips. Screenshot inspected: centered
readable dialog, focused name field, unobscured actions. This is UI evidence, not
physical capture, real provider, TLS or deployed G8 qualification. No sound, device
capture, permission request or volume change occurred. Browser and dev server closed.

Adversarial review found two reachable unattributed-speech failures: a null canonical
ID rejected the entire saved-history response, and the S00 chip offered an impossible
naming action. Fixed: omit absent canonical identity in saved Live rows, retain their
S00/text, and disable S00 naming. Backend document and frontend parsing/view tests
cover mixed attributed/unattributed output. Label-only revision behavior, duplicate
identity separation and Stop/observer controls had no other must-fix finding.
