# S9 negative-credit control

The retained rejected S9 receipt showed impossible negative credits. Source-interval
overlap prevents cross-interval matches, but it did not prevent a word from receiving
credit before its own source interval had finished.

Control:
`tests/test_visible_word_instrument.py::test_word_is_not_credited_before_its_source_interval_finishes`

- Before correction: FAIL, observed first-correct `3.0 s` for a source interval ending
  at `10.0 s` (expected first eligible observation `11.0 s`).
- After correction: full visible-word suite PASS, `10 passed in 0.04s`.

Rule: matching remains ordered and interval-overlapping; a surface observation cannot
credit a reference word until the independently authored source interval end is reached.
This introduces no latency target.
