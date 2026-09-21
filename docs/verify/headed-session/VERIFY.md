# Verification

Run the one-command browser probe from this clone with a new output path. Expect a JSON result with `headless: false`, exactly `--mute-audio`, `navigation_http_status: 200`, marker `headed DOM`, and positive `outer_html_length`. Any launch/navigation/marker/DOM failure falsifies RUNNABLE-HERE.

Use the disposable runtime for the short stack arm: `/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python` must report exactly SQLite 3.53.4. Its synthetic-local control must close/finalize and record a nonempty rendered-DOM measurement; it is wiring evidence, not ASR quality.
