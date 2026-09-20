# VERIFY RESULT — R4-8 surfaces

**PASS, with fresh-context limitation.** `VERIFY.md` was executed literally in the
current session because this interface does not expose `/new`; this is not the required
independent fresh-context session.

- Source: `89f833acd4c654dd702664a17ed19783a2999c95`, branch `round4/surfaces`.
- Syntax: four Python files compiled; shell syntax passed.
- Hidden gate: exit 77, `BLOCKED-ON-SESSION`; no browser launched.
- Summary dry-run: case 13 provider POSTs 0; verifier exits 0, 1, 77.
- New/owned secret-pattern matches: 0. Base has seven documented `<key>` placeholders.
- Owned listeners after run: none on 18442, 18443, or 18733.
- Backend full suite: 2116 passed, 5 skipped, 37 subtests.
- Frontend: 311/311; TypeScript and Vite build clean.

Hidden behavior, m4mbp forwarding, microphone, playback, capture, voiceprints, decoder
reachability, and real-provider semantics remain unverified as stated in `NOTES.md`.

## Lead-issued fresh context — 2026-09-20

**FAIL.** Steps 2–6 passed; step 1 failed its literal HEAD requirement.

1. **FAIL** — branch `round4/surfaces`; starting HEAD
   `de0a44129fa609ed71e3b655d9d250f2e205d94d`, not prefix `89f833ac`.
2. **PASS** — Python compile `4/4`; `sh -n` `1/1`.
3. **PASS** — Background gate exit `77`; `BLOCKED-ON-SESSION` `1/1`; no browser
   launch path reached.
4. **PASS** — case 13 provider POSTs `0`; verifier exits `0, 1, 77`; runner exit
   `0`.
5. **PASS** — owned secret-assignment matches `0`; base `<key>` assignment
   placeholders `7`.
6. **PASS** — owned listeners: port 18442 `0`, 18443 `0`, 18733 `0`; owned
   surface processes `0`.

No off-host request was permitted by the loopback sandbox. Hidden behavior, m4mbp,
microphone, audio, and playback were not measured.
