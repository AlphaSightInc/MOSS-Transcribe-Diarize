# Capture-layout policy verdict

Question: should malformed HAL/microphone producer shapes fail closed, truncate to
the shortest member, or zero-fill missing channel tails before production downmix?

**VERDICT: FAIL CLOSED (2026-08-03).** One valid two-channel rectangle produced
`[0.500, 0.500, 0.500]` under all three policies, so the decision does not change
valid-path audio. For unequal 3-frame/2-frame planar buffers, truncation returned
`[1.000, 1.000]` and silently discarded one valid frame; zero-fill returned
`[1.000, 1.000, 0.500]`, corrupting the truthful 1.000 tail by -0.500. The production
policy instead returned the typed empty discontinuity. Real partial-interleaved,
nil-data, zero-channel, non-Float-aligned HAL values and a non-Float microphone
`AVAudioPCMBuffer` also produced empty discontinuities with no fabricated samples.

Command: `bash prototypes/capture-layout-policy/run.sh`. Evidence was captured under
`/tmp/moss-closure-3232375-evidence/c1/` with rc 0. The optional shared factory was
not adopted: the two constructors are small and lane-specific, while changing product
code would add churn without changing or strengthening the measured policy.
