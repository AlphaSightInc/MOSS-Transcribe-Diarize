# First voice-bank match latency

Question: is an eligible voice-bank observation delayed by album admission, a sweep, or publication?
Contract/falsifier and full pipeline trace: docs/audits/voiceprint-first-match-20260911.md.

The real trace falsifies the proposed bank-trigger diagnosis: the first causal commit was named in the next snapshot ~10ms later. Its vector already bypasses the 2s album gate legitimately under ADR-0009's separate >=1s observation rule. No new bank-match trigger is justified.

Hash probe: `hash_probe.py` runs the pinned production encoder before/after a throwaway stat-keyed verification reuse. `hash-results.json`: 34ms hashing out of 343ms embedding, identical vectors. No production cache selected; this cannot account for seconds of latency.

First-decode scheduling prototype: on the isolated 17863 stack only, override `EndpointPolicy._next_hard_boundary` to return `min(normal, ALBUM_ADMISSION_SECONDS * 16000)` while `_open_start == 0`, then use the original boundary for all later spans. All identity thresholds unchanged; this DOES change the first decode geometry, so it is not being presented as a policy-neutral bank-match fix. Original 17861 stack never altered.

The first 2s trial queued at 2.648s but decoder latency rose to 1.078s; visible name arrived at 4.114s. No latency improvement established from that sample. A warm repeat reached 3.2926s, still FAIL against <=3s. The change advances evidence availability but does not establish the demo target; shared decoder variation remains material. Prototype launcher remains `/tmp/moss-row10-stack/run_first_span_prototype.py`; original isolated launcher `/tmp/moss-row10-stack/run_local_stack.py`. Both use separate state/control paths and the user's existing tunnel/cert.

Measurement repair: Playwright's locator polling inflated Start-to-name by hundreds of milliseconds. The harness now observes and timestamps the visible DOM mutation; polling only waits for the recorded result. On unmodified current product code, the corrected measurement is 3.7007s (FAIL against <=3s), with first canonical processing completed at 3.689s. This is measurement correction, not a product speedup.

Operator resolution: retain the original 2.5s decode cap and all policies. Adopt a derived 4.0s regression budget (2.5 + 1.0 + 0.5); the existing 3.7007s baseline passes. The earlier-boundary experiment is rejected for shipment. No production endpoint changes exist. See the audit's Approved resolution and retained approved-verdicts.json.
