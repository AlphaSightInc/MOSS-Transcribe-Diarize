# R4-5 fresh-context verification result

Outcome: **PASS**.

Executed `VERIFY.md` literally from `/private/tmp/moss-round4-20260920/batch` at
`c8ca897d83e3ff9844902b8e8ff28a9af6b88760`:

1. **PASS — merge base:** `89f833acd4c654dd702664a17ed19783a2999c95`.
2. **PASS — branch:** `round4/batch`.
3. **PASS — deterministic prototype:** `SUPPORTED`; 10/10 cases supported;
   C1 made 61 calls and saved 101/101 unique segments; C10 interrupted Live and
   left 0 active rows; 0 decoder requests used.
4. **PASS — violating controls:** 2 xfailed in 2.64 s; 0 failed; 0 xpassed.
5. **PASS — real runner:** `SUPPORTED`; completed; 3 transcript segments / 120
   generated characters; 9.025 s; 0 remote decoder requests; network disabled.

No GPU, tunnel, network, or product change was used.

## Historical current-context result

Outcome: **PASS in current context; fresh-context gate PENDING**.

`VERIFY.md` was executed literally after commit `5505b1cb`:

- Parent: `89f833acd4c654dd702664a17ed19783a2999c95`.
- Branch: `round4/batch`.
- Deterministic prototype: `SUPPORTED`, 10/10 cases.
- Base violating controls: 2 xfailed in 2.97 s.
- Local-HF smoke: `SUPPORTED`; completed; 3 segments / 120 characters;
  10.823 s; zero remote requests.
- Working tree after verification: clean.

The pane environment cannot self-issue `/new`. Therefore this file does **not** claim
the required fresh-session verification. A lead or replacement session must run
`VERIFY.md` once; no other work remains for that gate.

The earlier mandatory full gate was also clean: backend 2,116 passed / 5 skipped /
2 expected xfailed / 37 subtests; frontend 311/311; TypeScript and Vite clean.
