# Manual naming lifecycle verdict

Real naming/store experiment, host SQLite 3.50.4, no audio:

- Cancel directly while the actual COMMIT has completed but its await is held:
  durable label = Durable; live label = S01; mutation cancelled.
- Keep the same mutation service-owned and shield transport cancellation:
  durable label = live label = Durable; mutation not cancelled.
- Pending sub-floor name followed by newly eligible Stop-tail evidence: one sample
  if cleared after observation; zero if pending admission closes at accepted Stop.

Verdict: reuse the existing service-owned-task primitive for accepted naming through
COMMIT, live-state publication and pending-intent registration. Lifespan joins it.
Close naming/enrollment admission at accepted Stop; clear pending before terminal
observations. Failure fencing must still claim publication before any cleanup await
(the already-settled lifecycle invariant), even when identity cleanup is locked.

The measured behavior is absorbed into the identity/live modules. Regression tests
must hold COMMIT and identity cleanup through real transport/Stop interleavings;
this experiment does not qualify the full deployed capture path.
