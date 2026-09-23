# D45 ruling prep (unmerged)

Structural question: can the existing quality producer report both raw DER axes and S00-unattributed DER axes, while the acceptance validator recomputes and bounds only the latter?

Minimum primitives: production settled `score_surface`, `calculate_diarization`, v2 reference-speech DER axis with its own VAD regions and optimal mapping, B2 speaker intervals, existing quality projection and validator.

Invariants: six cases/two passes and all bounds/tolerance unchanged; each raw axis keeps its own optimal mapping, miss, and false alarm. Named-speaker confusion stays chargeable. S00 overlap with reference is unattributed: excluded from confusion, never credited as correct even when S00 is mapped to a reference speaker. No product scorer, word/content, request, or population change.

Assumptions/unknowns: the real D45 O1 replay summary has per-case full DER/S00-excluded DER but no retained reference-speech counterfactual. H1 raw rows predate B2 retention and cannot reconstruct reference-speech S00 timing. The real replay's `without_s00_confusion` diagnostic uses rounded fixed mapping; any mapped-correct S00 time needs a separate charge.

Falsifier: a named-speaker confusion case passes the unchanged bound; S00 mapped correct receives credit; the producer's raw score differs from either production scorer; or the validator admits an inconsistent raw/adjusted projection.

Tools: focused RED/GREEN tests on production scorer/projection/validation establish the changed decision; D45 summary replay checks the observed DER macro; full backend and bundle check unrelated acceptance paths.

Ranked hypotheses (diagnose):
1. Projection and validator exclusively use raw settled `der`/`reference_speech_der`; exposing adjusted values there changes only the acceptance decision. Prediction: S00-only bound failure turns PASS, named confusion remains FAIL.
2. The two DER axes use different optimal mappings and reference regions. Prediction: subtracting the same S00 fraction from both disagrees with the reference-speech scorer.
3. S00 can be an optimal mapped label. Prediction: subtract-only logic would credit mapped-correct S00; charging that time as unattributed prevents a free pass.
