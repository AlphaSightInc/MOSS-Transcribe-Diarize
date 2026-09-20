# WP54b unpatched controls

- Base: `a7a738cf9f9ff246f64c52c112e0bf597ba58241` in a disposable detached worktree.
- Command: `python -m pytest -q -p no:cacheprovider tests/test_visible_word_instrument.py`.
- Result: **FAIL as required**, exit 2; `1 error in 0.06 s`.
- Failure: `ModuleNotFoundError: tools.qualify.visible_words`; the unpatched
  candidate had no ordered source-word visibility instrument and therefore
  could not retain wrong/omitted reference words in a latency denominator.
