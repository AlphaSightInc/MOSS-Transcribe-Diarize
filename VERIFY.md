# Verification

Run the one-command browser probe from this clone with a new output path. Expect a JSON result with `headless: false`, exactly `--mute-audio`, `navigation_http_status: 200`, marker `headed DOM`, and positive `outer_html_length`. Any launch/navigation/marker/DOM failure falsifies RUNNABLE-HERE.

Do not run the short stack arm as a passing control on this host: its expected, evidence-preserving outcome is SQLite-runtime refusal before decoder dispatch.
