"""WP30 measurement only: observe production owners; never alter lifecycle/policy."""
import dataclasses
import gc
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import tracemalloc
import weakref


def install(state):
    from moss_transcribe_diarize.app.live_service_runtime import LiveServiceRuntime
    from moss_transcribe_diarize.app.live_v2_session import LiveV2Session
    runtimes, sources = [], []
    original_runtime = LiveServiceRuntime.__init__
    original_source = LiveV2Session.__init__
    def runtime_init(self, *a, **kw):
        original_runtime(self, *a, **kw)
        runtimes.append(weakref.ref(self))
    def source_init(self, *a, **kw):
        original_source(self, *a, **kw)
        sources.append(weakref.ref(self))
    LiveServiceRuntime.__init__ = runtime_init
    LiveV2Session.__init__ = source_init
    tracemalloc.start(1)
    def monitor():
        while True:
            command = state / 'checkpoint'
            checkpoint = command.read_text() if command.exists() else None
            row = dict(time=time.monotonic(), checkpoint=checkpoint, pid=os.getpid(), runtimes=[])
            for ref in runtimes:
                runtime = ref()
                if runtime is None:
                    continue
                with runtime._lock:
                    sessions = []
                    for sid, s in runtime._sessions.items():
                        c = s.coordinator
                        snap = s.session.snapshot()
                        owners = {}
                        for lane, p in (c._lane_preparers or {'mono':c.identity_preparer}).items():
                            e = getattr(p, 'evidence_provider', None)
                            album = getattr(e, '_album', None)
                            sweep = getattr(e, '_sweeper', None)
                            owners[lane] = dict(album_entries=sum(len(v) for v in album._exemplars.values()) if album else 0,
                                pending_vectors=len(getattr(e, '_pending_vectors', {})),
                                sweep_spans=len(sweep.ledger._spans) if sweep else 0)
                        tapes = {'mixed':c.tape, **c.lane_tapes}
                        sessions.append(dict(id=sid, status=snap.status, finalization=snap.finalization_status,
                            accepted=snap.accepted_samples, accounted=snap.accounted_samples,
                            queues=dataclasses.asdict(s.arbiter.snapshot()), owners=owners,
                            events=len(s.events), frames=len(s.session._frames), spans=len(s.session._frozen_spans),
                            tapes={k:len(t._buffer) for k,t in tapes.items() if t is not None}))
                    row['runtimes'].append(dict(pending_signals=runtime._canonical_scheduler.pending_signals,
                        in_flight=runtime._canonical_scheduler.in_flight, ready=len(runtime._ready_session_ids),
                        sessions=sessions))
            row['replay_acks'] = [len(ref()._ingress._acks) for ref in sources if ref() is not None]
            row['rss_bytes'] = int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())],text=True))*1024
            row['python_bytes'], row['python_peak'] = tracemalloc.get_traced_memory()
            if checkpoint:
                # Native RSS and traced Python bytes are separate measurements.
                shot = tracemalloc.take_snapshot()
                row['allocations'] = [dict(location=str(x.traceback[0]), bytes=x.size, count=x.count)
                                      for x in shot.statistics('lineno')[:40]]
                del shot
            with (state/'telemetry.jsonl').open('a') as stream:
                stream.write(json.dumps(row)+'\n')
            if checkpoint:
                command.unlink(missing_ok=True)
                (state/'checkpoint-done').write_text(checkpoint)
            time.sleep(5)
    threading.Thread(target=monitor, daemon=True, name='wp30-observer').start()
