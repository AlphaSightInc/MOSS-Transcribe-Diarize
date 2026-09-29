"""Saved usage arithmetic; no Gemini request."""
from moss_transcribe_diarize.app.gemini_provider import _usage_cost

usage = {"input_tokens_by_modality": [{"modality": "audio", "tokens": 100}],
         "total_output_tokens": 10}
metered_input_usd = 100*2/1_000_000
metered_output_usd = 10*12/1_000_000
print({"metered_input_usd": metered_input_usd,
       "metered_output_usd": metered_output_usd,
       "cost_usd": _usage_cost(usage),
       "sum_matches": metered_input_usd + metered_output_usd == _usage_cost(usage)})
