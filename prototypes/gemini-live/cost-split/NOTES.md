# Metered cost split

Question: how much of `cost_usd` is provider-metered output, so the scorecard can add an output estimate only to metered input? Primitives: provider input token charge, provider output/thought token charge, total cost, and separate list-price output estimate. Invariant: `cost_usd = metered_input_usd + metered_output_usd`; estimates do not enter that sum. Unknown: whether provider bills all reported thought tokens at the quoted rate. Falsifier: saved usage arithmetic does not sum to the existing cost or the new field changes cost.

Tool decision: one local arithmetic probe of the existing production `_usage_cost` formula, using a saved fixture shape, avoids provider spend and gives a checkable split.

Run from WP1: `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/cost-split/probe.py`

Measured fixture: 100 audio-input tokens yield $0.00020 input; 10 output tokens yield $0.00012 output; existing `cost_usd` is $0.00032, exactly their sum. Keep the independent output estimate out of `cost_usd`. Runtime diagnostics also contain a separately identified live list-price estimate; a scorecard deriving metered input from the aggregate must subtract both `metered_output_usd` and `live_list_price_estimate_usd`.
