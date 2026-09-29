# S1 cached-output label-stall probe

**Structural question:** Why did the paced long60 run keep making Gemini rolling calls after 750 s while speaker-labelled rows stopped there and the public audio frontier continued to 2,580 s?

**Minimum primitives:** the public long60 PCM; exact cached Gemini 3.5 Transcribe response for each growing S15/L90 window; production timestamp repair, word gate, WeSpeaker embeddings and continuity registry; production two-lane engine, runtime and LiveSession; content-free per-window frontiers/publication/exception trace. Each is necessary to distinguish response, mapping, lane, and runtime failure. Silent mic and a no-op Live word source isolate the batch path.

**Invariants:** use integration modules only, confirmed by module paths; cache miss raises before any network call; no key/client construction; every accepted sample advances contiguously; no product edit; no audio or secrets in receipts. Accelerated replay can prove a deterministic output-path defect, not 1.0× latency.

**Assumptions and unknowns:** P1 cached the same 172 complete 15-second ticks (preflight: 172/172 hits); the final 6-second suffix is not decoded because the probe does not Stop. No-op Live words and absent WP4 tentative hook differ from the paced run. Real-time scheduling and transient provider errors are not reproduced.

**Hypotheses/falsifiers:** H1 cached words/timestamps fail at the first post-750 window → a caught exception names that window. H2 WeSpeaker/registry stops mapping → decoded windows continue while mapping is missing/refused. H3 silent mic blocks publication → system frontier advances but mic/public frontier stays 750 s. H4 no cached-only failure → all frontiers/labels advance past 750 s, leaving Live words, tentative hook, or pacing as the remaining differences.

**Tool decision:** one command runs the probe with `PYTHONPATH=<integration worktree>` and `PYTHONDONTWRITEBYTECODE=1`; it writes JSONL events and a JSON summary to the supplied evidence directory. Real cached outputs are necessary because 1 ms, 50 s, and raised fake diarizers did not reproduce. The production encoder and registry expose the first failing mapping; no Gemini call could improve this zero-spend diagnosis.

Command:

```sh
PYTHONPATH=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-r2-int PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/s1-cached/probe.py --out /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P66/wp3/s1-cached
```

## Verdict — reproduced, root cause isolated

Integration HEAD `58fced82c958d619cc437d3a2e87fde39c4d1344`, read-only. The probe printed module paths inside that worktree. One full accelerated replay of the public 2,586 s long60 WAV: **172/172 exact scheduled windows cached, 0 cache misses, 0 Gemini sends, $0 spend**. System decoded 172 cached responses; silent mic made 0 provider calls. Both lane frontiers reached 2,580 s, while the public rolling frontier and last labelled row stayed at **750 s** after exactly **50 rolling publications**. Committed audio reached 2,580 s through fallback. The trace recorded 122 worker exceptions after the first at 765 s. Receipt: `evidence/P66/wp3/s1-cached/{events.jsonl,summary.json}`.

**First failure:** the cached 675–765 s system window has 295 parsed words; 54 pass the word-end selection for the 750–765 s publication. Annotation order ends with a 764.9–765.0 s word followed by a 763.1–763.4 s word. `ordered_segments(..., preserve_order=True)` folds the fully overlapped final word into the prior row. In `gemini_provider.py:130-131`, that reconstruction copies time/text/speaker but omits `prior.source_lane`; direct replay of the cached window yielded one 764.9–765.0 s row with `source_lane=None`. `LaneGeminiEngine._rows_in` sorts with `self.LANES.index(row.source_lane)` (`gemini_lane_engine.py:560-564`) and raises `ValueError: tuple.index(x): x not in tuple`. At the 765 s frame both lane frontiers were 765 s, public frontier 750 s, committed 765 s. The malformed row remains in the lane's retained rows, so each subsequent public publication re-sorts it and fails. No mic-frontier stall or missing registry mapping: the 765 s system mapping was `spk:0→speaker-0001`, `spk:1→speaker-0002`.

**Minimal failing regression sketch (lead-owned product tests):** construct two `GeminiSegment` values on `source_lane="system"`, the first ending at the publication boundary and the second fully overlapping it but appearing later in annotation order. Assert `ordered_segments((first, second), start_sample=..., end_sample=..., preserve_order=True)[-1].source_lane == "system"`. Then replay the exact cached 675–765 s window through the two-lane engine after a 750 s frontier and assert the 765 s `GeminiRolling` publication succeeds and labels resume. The minimal production correction is to pass `prior.source_lane` when reconstructing the final row; no product code was edited in this package.

**Limit:** Live words were a no-op, the WP4 tentative hook was absent, and frame feeding waited for cached work rather than running at 1.0×. Those differences did not prevent this exact 750 s stall, so they are not necessary for this failure. This probe does not measure live latency or guarantee all other paced-run defects are gone.

**SHA custody:** the full replay started when integration HEAD was `58fced82c958d619cc437d3a2e87fde39c4d1344`. During the run, the lead advanced it to `4565db2db47554d7b139ee46a7ec071d868cd7d6` by merging WP1's Stop-tail and cost-split fixes and updating docs. A read-only diff confirmed those changes do not alter `ordered_segments`' lane-dropping branch or ordinary rolling publication; the branch remains at lines 130–131 on the newer head. The loaded Python modules came from the launch SHA. Future probe runs now record `source_sha` directly in their summary.
