# Fix publication evidence

## Structural contract

- Question: how can one unresolved speaker identity remain the same from persistence and API projection through JSON export, while human-readable downloads remain readable?
- Minimum primitives: canonical machine identity `S00`; display label `Speaker uncertain`; export oracle comparing each download with the API meeting document.
- Invariants: unresolved identity is never presented as an identified person; JSON preserves the API identity; Markdown, text, SubRip, and WebVTT contain the display label and no literal `S00`; reserved uncertainty labels remain unavailable as user-assigned names; known speakers are unchanged.
- Assumptions/unknowns: `UNKNOWN` remains accepted as an existing preview/legacy input but is not emitted as the persisted/exported unresolved identity. No decoder behavior is changed or measured.
- Falsifier: any JSON/API unresolved-id mismatch, literal `S00` in a human-readable download, reserved-label regression, or known-speaker export regression.
- Tool decision: deterministic serializer/oracle tests reach the production export path and can distinguish every falsifier. Decoder/GPU work cannot change this decision and the brief grants zero requests.

## Custody and diagnosis

- Clone: `/private/tmp/moss-round3-20260919/fix-publication`
- Branch: `round3/fix-publication`
- Base: `738cdfdde092b8ba9341179fb1d33e1c34cbd24c`
- Stress evidence: `/private/tmp/claude-501/stress/C/runs/probe_s11_review.py` and `s11-review/probe.log` show API `speaker_entity_id=S00`, JSON oracle `identity=false`, and the other four formats oracle-equal.
- Root cause: the JSON serializer rewrote unresolved `speaker` and `speaker_entity_id` to `UNKNOWN`; the existing oracle repeated that rewrite and therefore hid the production mismatch.
- Failed bootstrap attempt: clone completed, but the first chained checkout ran from the parent directory and returned `fatal: not a git repository`; checkout was rerun inside the verified clone.

## Violating control on unpatched base

Command:

```text
npm --prefix frontend test -- --run src/lib/transcriptExport.test.ts -t 'keeps the API unresolved identity in JSON exports'
```

At unpatched `738cdfdd`: FAIL, 1 failed / 17 skipped. Expected `S00`; received `UNKNOWN`.

## Patched focused controls

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <mandated-python> -m pytest -q -p no:cacheprovider tests/phase2/test_export_oracle.py
84 passed in 2.07s

npm --prefix frontend test -- --run src/lib/transcriptExport.test.ts src/lib/speakerMap.test.ts
33 passed across 2 files in 158ms

npm --prefix frontend run typecheck
PASS

npm --prefix frontend run build
PASS, 34 modules, 101ms
```

- Healthy matrix: 10/10 production exports oracle-equal (five formats x live/file source shapes), including a needs-review unresolved segment.
- JSON: canonical machine identity is `S00` for both `speaker` and `speaker_entity_id`; display remains `Speaker uncertain`.
- Human-readable downloads: 8/8 live/file x md/txt/srt/vtt contain no literal `S00`.
- Reserved-label and export controls: 33/33 frontend tests passed.
- Decoder/GPU: 0/0 requests; lease untouched; no tunnel opened.

## Interpretation of “downloaded text”

JSON must contain the canonical `S00` machine field to equal the API document. Therefore the no-literal-sentinel assertion applies to the four human-readable text formats; their visible label is `Speaker uncertain`. Applying it to raw JSON would directly contradict the required JSON/API equality.
