# Local qualification bundle

From the checkout to measure:

```sh
bash scripts/mvpfix-qualify.sh --long --budget 3500
```

Exit 0 requires all requested gates PASS, with explicit optional SKIPs allowed. Exit 1
retains failures and missing observations. Results live in
`evidence/mvpfix/wp25/<measured-sha>-<utc>/summary.{json,md}`; `--out DIR` changes the parent.
`--compare SUMMARY` compares every gate's status. A short rerun explicitly separates
file_30min/capacity_2x1800 omissions from unexpected changes; SHA equality is reported.
The short run includes three-minute WAV/MP3/M4A files and a six-minute WAV.
`--long` adds one 30-minute WAV and two simultaneous 30-minute Live sessions
(monologue plus panel). Four-live capacity is historical, superseded by the two-meeting contract.
Without it those gates are SKIP, never measured PASS.

Requires existing Python venv (`MOSS_QUALIFY_PYTHON` override), node_modules symlink,
npm/Node, ffmpeg/ffprobe, local model metadata/provider assets, SSH access, Playwright
browser. No install, host trust update, service restart, or deployment occurs.
Ports: owned SSH tunnel 18125; counted proxy 19125; main/browser/capacity stacks
17825/17826/17827; HTTPS/hung media origins 17828/17829. Occupied ports are UNRUNNABLE.
Default budget 2000; `--budget N` sets the exact dispatch ceiling across every stack
and browser restart. Maximum two own requests in flight. Shared GPU contention is
sampled every two seconds; no sibling-load pause. Existing capacity clean verdict
still rejects detected foreign load and reports its other measurements separately.

All benches retain existing case bodies and product bars. Browser all runs headed
for native visibility cases and owns its restartable stack. File failures preserve
WP16's typed failure, reason visibility, reload and foreign-owner predicates; successful
files require all five exact exports and downloaded audio. Ordered word error and per-person source-turn speaker scores are reported
against the composed reference. Entirely missing people remain visible even when aggregate scores pass. No new quality threshold. Identity runs single/gap/
alternating; each requires one distinct saved identity per reference voice, no switches
or unresolved segments. Ladder runs the original lead script (`--ladder PATH` override),
all six points. PASS means finalized measurements; retained vocabulary counts are
compared with the lead separately and are not transcript-accuracy claims.

Scratch, audio, snapshots, raw stdout, browser profiles and TLS keys remain ignored
under `.wp25runtime/`; the manifest preparer uses checkout-local `.wp6-tmp/`. The admitted
manifest copy allows 57,600,000-byte tape; original untouched. The existing local recipe
bypasses SQLite's exact runtime pin, so this is not deployed-runtime qualification.
WP16's path-only test plugin confines inherited /tmp fixtures. Vite's native loader
avoids writes through shared node_modules. Loopback CA trust is process-local.

Only content-safe counts/statuses/measurements are retained. Summary row requires an
environment API key; a key alone does not configure the relay. Without a key it is
SKIP with reason. Missing bench output is UNRUNNABLE, never a fabricated PASS.
Tree cleanliness is recorded before output creation. Commit prior evidence before
rerunning. Owned process groups, proxy, tunnel and sampler are stopped in finally.

Round 2: use `--decoder-upstream-port PORT` to share an already-owned counted decoder.
The source-turn speaker score has no boundary collar or fitted time offset; it is not a fine
acoustic diarization benchmark. Physical microphones, attended echo cancellation, and any
browser state the harness cannot actually produce remain unmeasured.
