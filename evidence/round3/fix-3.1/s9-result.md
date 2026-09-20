# S9 headed visible-word result

- Input: one 300.0 s live session; 25 source intervals; 889 reference words; exact retained system/microphone WAVs.
- Browser: headed Chromium, `--mute-audio`; 601 visible observations; document stayed visible, so hidden-tab behavior is `UNMEASURED`.
- Terminal: meeting `closed`; finalization `final`.
- Decoder: 160/250 requests; peak concurrency 1; 160 additional `stop` outcomes; length/failure counters unchanged; post-run running/waiting 0.
- API: 856 correct, 20 wrong, 13 missing / 889. Finite-only first-correct p50 1.478 s, p95 10.040 s; stable-correct p50 1.478 s, p95 11.980 s. Full-population percentiles are `null` because 33 words are wrong/missing.
- DOM: 842 correct, 29 wrong, 18 missing / 889. Finite-only first-correct p50 0.358 s, p95 6.531 s; stable-correct p50 0.358 s, p95 9.407 s. Full-population percentiles are `null` because 47 words are wrong/missing.
- Contract checks: every wrong/missing word has `null` first/stable clocks; all 889 rows remain in each denominator; negative latency count 0; bucket-only evidence refusal control passes.
- Post-run projection fix: 11 API and 10 DOM finally-wrong/missing rows had retained an earlier correct time. Added a violating control, nullified those fields, and recomputed distributions from retained per-word rows; no decoder rerun.
- Server clocks retained: 189 content-free events (130 canonical, 29 rolling queued, 29 rolling completed, 1 terminal start); clocks remain separate from browser/API clocks.
