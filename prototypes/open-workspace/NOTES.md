# Open workspace sentinel probe

## Question

Can concurrent cookie-less requests create and reuse one durable Account/session pair
with the existing SQLite schema and mutation boundary?

## Hypothesis and falsifier

`INSERT OR IGNORE` for one fixed Account and session produces one binding and one row
per table, including after database reopen. More than one binding or row, or a missing
binding after reopen, rejects the design.

## Command

```sh
.venv/bin/python -m pytest \
  tests/phase2/test_browser_workspace.py::test_open_workspace_binds_independent_clients_to_shared_history -q
```

## Verdict

**Accepted.** Twenty concurrent bindings produced one `open-workspace` Account/session
pair, exactly one row in each table, and the same Account after database reopen. The
macOS semantic probe used the repository's established local SQLite-version override;
the full suite separately checks the pinned production runtime. The throwaway probe was
then absorbed into the regression above.
