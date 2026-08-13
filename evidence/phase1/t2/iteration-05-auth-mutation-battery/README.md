# Iteration 5 — unchanged auth mutation-battery audit

Target branch HEAD: `65e46b1842c866ebc8edf07986e83112bc1412a3`.

The two A-025 reviewer harnesses were copied byte-for-byte from the historical control plane and
run against local isolated clones. `harness-sha256.txt` proves the source/copy pairs are identical.
No production service or remote host was touched.

## Results

- `control.json` and `transcript.txt`: the re-review runner passed unmutated controls U, A, C, B,
  S, L3, and D. Control R exited 1 because the old spike omits today's required
  `live_helper_lease_seconds`, so the runner aborted before mutations.
- `original-battery-transcript.txt`: the original unchanged runner killed M01 through M16 (19
  rows including M04b, M09b, and M12b), then aborted because M17's old view-expiry anchor occurs
  zero times.
- `control-R-stderr.txt`: raw traceback for the stale R control.
- `repository-state.txt`: branch and clone HEADs plus status output after the runs.

This does not prove 33/33. It proves the historical battery is stale on two seams introduced before
ticket #2. No historical cross-read `403` result was used as an acceptance gate.
