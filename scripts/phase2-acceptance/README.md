# Acceptance profile content boundaries

`profile.example.json` retains five browser-workspace boundary roles in each
measurement layer: two owner sentinels and three session credentials (owners A,
B and the revocation probe). D1 retires Google credentials, not these boundaries.
The pre-admission layer has independent credentials and sentinels; each owner's
peer shares its cookie. All ten files must be mode 0600, nonempty and distinct.

The `qualification-attempt` paths describe the layout created by
`prepare_acceptance_profile`: `<attempt>/acceptance-private/<layer>/...`.
They are not pre-existing credentials. Normal cutover setup creates fresh
workspaces through the application's HTTPS bootstrap, generates the private
files and replaces these paths with the actual attempt directory. It passes
`<attempt>/acceptance-private/profile.json` to the acceptance driver.

For an already prepared candidate attempt, use that generated profile with
`run.py --profile <attempt>/acceptance-private/profile.json`. Copying the example
alone does not provision workspaces. Do not invent placeholder cookie contents,
reuse an earlier attempt's credentials, or remove `forbidden_files` to bypass
setup. Missing files must remain a qualification refusal.

Regression command:

```sh
.venv/bin/python -m pytest -q tests/phase2/test_acceptance_setup.py
```

This loads the shipped template and exercises real application bootstrap and
the unchanged content-boundary loader against disposable SQLite state. It
checks all ten generated files, six independent owners and shared peer cookies;
it does not establish deployed TLS trust or qualification.
