#!/bin/zsh
set -eu

repo_root="${0:A:h:h:h:h}"
cd "$repo_root"
export NO_COLOR=1

dev_revision="$(git rev-parse dev)"
head_revision="$(git rev-parse HEAD)"
if ! git merge-base --is-ancestor dev HEAD; then
  print -u2 "FAIL: dev ${dev_revision} is not merged into HEAD ${head_revision}."
  exit 1
fi

print "dev=${dev_revision}"
print "head=${head_revision}"
print "dev_is_ancestor_of_head=true"
print '$ PYTHONPATH=. .venv/bin/python evidence/phase1/x4-journal-mode/probe-preexisting-modes.py'
PYTHONPATH=. .venv/bin/python evidence/phase1/x4-journal-mode/probe-preexisting-modes.py
print '$ PYTHONPATH=. .venv/bin/python evidence/phase1/x4-journal-mode/probe-batch-loss.py'
PYTHONPATH=. .venv/bin/python evidence/phase1/x4-journal-mode/probe-batch-loss.py
print '$ PYTHONPATH=. .venv/bin/python evidence/phase1/x4-journal-mode/probe-reader-contract.py'
PYTHONPATH=. .venv/bin/python evidence/phase1/x4-journal-mode/probe-reader-contract.py
print '$ PYTHONPATH=. .venv/bin/pytest -q tests/test_live_service_runtime.py tests/test_live_api.py'
PYTHONPATH=. .venv/bin/pytest -q tests/test_live_service_runtime.py tests/test_live_api.py
print '$ PYTHONPATH=. .venv/bin/pytest -q tests/test_live_provider_bundle.py'
PYTHONPATH=. .venv/bin/pytest -q tests/test_live_provider_bundle.py
print '$ python3 scripts/afk-guardrails/preflight.py x4-journal-mode'
python3 scripts/afk-guardrails/preflight.py x4-journal-mode
