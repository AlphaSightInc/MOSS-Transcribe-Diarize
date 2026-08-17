# Reference UI screenshot tolerance prototype

## Question

Does exact RGB inequality misclassify imperceptible browser rasterization as a large connected
fidelity failure, and what is the smallest channel tolerance that removes it without changing the
charter's 2% differing-pixel or 1% connected-region bars?

## Command

Run the existing two-viewport probe, then recompute its saved reference/candidate images at channel
tolerances 0, 1, 2, and 3 while applying the report's exact exemption boxes:

```sh
PYENV_VERSION=3.12.12 pyenv exec python tests/reference_ui_screenshot_diff.py \
  --output evidence/phase1/g8-toolbar-structural-20260817
```

The recomputation used `max(abs(reference_rgb - candidate_rgb)) > tolerance` and the production
probe's four-connected component rule.

## Measurements

| Case | Viewport | tolerance 0 | tolerance 1 | tolerance 2 |
|---|---:|---:|---:|---:|
| candidate | 1440x900 | 0.598% / 0.271% | 0.290% / 0.078% | 0.208% / 0.076% |
| candidate | 1280x800 | 4.659% / 3.740% | 1.751% / 0.570% | 0.616% / 0.279% |
| reference self-check | 1440x900 | 0.340% / 0.268% | 0.085% / 0.001% | 0.000% / 0.000% |
| reference self-check | 1280x800 | 0.471% / 0.376% | 0.408% / 0.327% | 0.352% / 0.279% |

Values are differing-pixel percent / largest four-connected-region percent. The 1280 candidate's
exact-RGB component contained 38,294 pixels; its median candidate-reference error was `[-1,-1,-1]`
and 99.98% of pixels were no lighter than the reference, identifying one-level shadow rasterization
rather than a visible layout region.

## Verdict

Accept channel tolerance 1. It is the smallest measured value that clears imperceptible
cross-context noise while preserving all differences larger than one RGB level. Keep the charter's
2% / 1% bars and exemption set unchanged. Tolerance 2 and 3 are rejected as unnecessary.
