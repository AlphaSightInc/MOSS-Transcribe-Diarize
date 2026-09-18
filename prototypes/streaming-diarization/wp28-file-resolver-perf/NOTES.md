# WP28 prototype contract

Q1: Where does file-album resolver time go, and which work can be removed without
changing any identity decision? Hypothesis: independent interval inference can
run concurrently while aggregation and album updates retain their original order.
P1: PCM interval -> normalized vector -> ordered mean -> ordered album update.
Intervals are independent acoustic observations; the mean and album depend on order.
I1: Same samples, features, vectors, reduction order, policy and complete output.
U1: Scaling, numerical equality and stage costs unmeasured at start.
F1: Any serialized IdentityResolution difference on retained 6/30-minute inputs
or the perfect-vector cases rejects the candidate. Inference failure must retain
existing abstention. Concurrency must close before a call returns, even on error.
T1: Profile production methods, then measure 2/4 workers against unchanged serial
output. No decoder load needed: identical WP19 retained windows and decodes copied
read-only into `.wp28runtime/real-{6,30}`. Source was WP16's alternating public clips.
The copy contains 3 and 15 windows respectively, not independent new speech.

One command (Python executable as COMMON.md):
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/streaming-diarization/wp28-file-resolver-perf/probe.py`
Candidate: same prefix, `WP28_WORKERS=2`, `parallel_prototype.py --arm parallel-2 --minutes 6`.
Full relevant album state is in each emitted JSON (window states + sweep), timing
summary on stdout, full byte comparator in ignored scratch (no words in git).
Verdict pending measurements. No production change yet.

## Verdict — accepted before production edits

Serial: 6 min 60.177873 s; 30 min 313.204362 s. Two workers: 6 min 30.714614 s.
Four workers: 6 min 17.715150 s, 30 min 91.808717 s. Complete serialized result
byte equality: 3/3 measured parallel runs. Perfect vectors: 4/4 (1/2 voices,
3/15 windows) byte-equal with expected canonical counts. Every probe retained:
107 / 575 intervals, 391.32 / 2059.98 audio seconds including overlap.
One ONNX session per arm/fixture. Session setup <.04 s; model rehash <1.5 s;
inference >99% of baseline embedding time. No reason to alter those minor costs.
Four-worker process peak: 1,349,009,408 bytes after 6+30 minutes (macOS ru_maxrss).
Two-worker six-minute peak: 1,006,338,048 bytes. Capacity with multiple files unknown.

Decision: compose the same single-thread ONNX session with four independent
interval workers only in the file album encoder. Four is justified by measured
3.4x speedup vs two's 2.0x, with bounded worker count; no new identity constant.
Preserve every probe and reduction order. Album updates cannot be parallelized
because each window depends on previous admissions; no order-independence claim.
Do not cap evidence at admission_seconds: that is admission eligibility, not a
license to change the vector's evidence. No threshold/policy changes.

The prototype is absorbed into the production encoder and the retained bench;
its temporary implementation will be removed after production equality tests.

Absorbed: `parallel_prototype.py` and `fake_probe.py` deleted after their measured
verdict; production owns scheduling and `tests/test_file_resolver_performance.py`
owns the perfect-vector, reverse-completion, failure/cleanup and real-fixture checks.
Retained `probe.py` profiles production by default; `--serial` selects the unchanged
serial scheduling path. `--arm NAME` saves a separate report and compares against
original baseline bytes. Historical candidate commands in COMMANDS.md refer to the
deleted throwaway; reproduce current scheduling through the product bench.
