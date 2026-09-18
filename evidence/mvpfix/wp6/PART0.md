# WP6 Part 0

Base: 37979e539f04d4ea740a1a94d021cd3bb894a0e2. Python imports confirmed inside this worktree.

Original ordered subset: 2 failed / 441 passed / 19 subtests passed.
The two failures were exactly SQLite 3.50.4 versus required 3.53.4.

Root cause: tests/phase2/conftest.py:10 registered the host-runtime adaptation as
a directory-scoped autouse fixture. In installed pytest 9.1.1, FixtureManager's
pytest_make_collect_report pops the pending conftest once and associates autouse
names with a Directory object; _getautousenames consults object ancestry.
Explicit arguments phase2/file, tests/file, phase2/file produce a second phase2
Directory object with no autouse registration. The failing tests' fixture closure
lacks permit_test_runner_sqlite. The production module object remains identical.
No earlier test/module import mutates the pin: the brief's import-leak premise is
falsified. Even test_live_mixer between the two Phase-2 files triggers the loss.
Every preceding file individually followed by the target collects the fixture.
See part0-collection.txt and part0-collection-narrow.txt.

Fix: register at tests/conftest.py (common ancestor), applying adaptation only to
Phase-2 paths. Production exact-runtime requirement remains untouched.

Validation: check_part0.py runs original order, reverse order, workspace lifecycle
suite including the explicit wrong-runtime rejection. Results: 443 passed + 19
subtests; 443 passed + 19 subtests; 15 passed. Each invocation has one existing
Starlette deprecation warning. The original multi-file reproduction is the
regression seam; no mock pin-only test substitutes for collection order.

Run with PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. and the brief's Python:
python evidence/mvpfix/wp6/check_part0.py

Boundary deviation: original reproduction used pytest's default temporary root
outside the worktree. All subsequent checks set TMPDIR to .wp6-tmp inside it.
No other checkout or shared service was modified.
