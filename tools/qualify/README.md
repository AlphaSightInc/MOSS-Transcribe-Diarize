# Local qualification bundle

From the checkout to measure:

```sh
bash scripts/mvpfix-qualify.sh
```

Exit 0 = PASS: every required gate passed. Exit 1 = FAIL (or determinism failure).
Exit 2 = INCOMPLETE: no failed gates, but required evidence is SKIP/UNRUNNABLE.
A failed gate takes precedence over incomplete evidence. `summary.json` records
`verdict` and `qualified`; the shell wrapper preserves the exit code. Workspace
summaries are required: missing relay/key remains a distinct SKIP row and makes
the workspace/bundle INCOMPLETE, never accepted. Only unrequested `--long` gates
are marked `required: false`; their default SKIP does not block a bounded run.
Standalone `verify_workspace.py`: 0 all selected rows PASS; 1 FAIL; 2 required SKIP;
77 browser unavailable.
Results: `evidence/qualify/<candidate-sha>-<utc>/summary.{json,md}`. `--compare <first-summary>`
adds an exact gate-name/status comparison (including added/missing gates). Runtime and
numeric observations may vary. `--long` requests 30-minute files and 4x600 capacity;
current unchanged scripts lack required isolation arguments, so those report UNRUNNABLE.
Default skips those explicitly. No optional skip is a measurement.

Dependencies: existing Python venv (override `MOSS_QUALIFY_PYTHON`), frontend installed
node_modules (worktree symlink), npm/Node, ffmpeg/ffprobe, local model metadata, existing
provider manifest/assets, SSH access to the documented GPU host, Playwright browser.
No installation/download/update is performed. Own ports: app 17867, tunnel 18121,
accounting forward 18122. Occupied ports cause UNRUNNABLE; never reuse a listener.
`--ladder PATH` supplies the original lead probe without modifying or copying its logic.
Budget default/maximum 300; `--budget N` lowers it. Maximum two own requests in flight.
Sibling decoder load does not delay or refuse dispatch; initial and subsequent contention
are retained. Unavailable required decoder metrics still yield UNRUNNABLE.

Isolated state uses a short relative Unix socket path inside `.wp21runtime/`. Existing
manifest copier writes `.wp6-tmp/` in this checkout; its admitted 57,600,000-byte copy is
used and identified by SHA. Original manifest remains untouched. Existing local launcher
bypasses SQLite's runtime version pin; these results do not qualify deployed runtime parity.
WP16's test fixture path plugin confines inherited hardcoded /tmp paths inside this tree.
Vite native configuration loading avoids writes through the shared dependency symlink.

No bench is rewritten, imported with replaced globals, or patched to invent support.
Browser all/WP16/capacity isolation gaps are listed explicitly. Summary row skips
with a reason without a recognized environment key. With a key, the unchanged bench uses
its existing relay configuration; a key alone does not configure that relay.
Ladder PASS means all six cases finalized; unique-vocabulary retention fractions are
reported against both alone controls. No unsupplied acoustic acceptance bar is invented.

Content-bearing stdout, TLS material, audio and snapshots stay in ignored runtime scratch.
Retained `.log` files are JSON projections of counts, statuses, durations and exceptions
by class only, not verbatim content-bearing logs. Decoder trace contains time/counts only.
Never add `.wp21runtime/`, `.wp6-tmp/`, or `.wp16runtime/` to Git. Bundle tree cleanliness
is sampled before the new evidence directory is created; prior uncommitted evidence is
reported as dirty. The shell trap signals the runner; its finally block stops owned process
groups, forward and sampler, then emits teardown status. SIGKILL cannot execute traps.

Identity single/gap/alternating use the existing fixed 17867 endpoint on the owned stack.
Their two inherited evidence files are backed up and restored byte for byte; only a
content-safe numeric projection enters this bundle. The verdict checks the prototype
invariant: one saved identity per reference voice, distinct voices distinct, no switches
or unresolved segments. Extra unused births are measurements, not collapsed into used IDs.
