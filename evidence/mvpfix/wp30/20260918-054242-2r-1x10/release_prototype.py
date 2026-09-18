"""THROWAWAY WP30 candidate: freeze final observations, drop mutable lane evidence.

Only imported by the bench with WP30_PROTOTYPE_RELEASE=1, after baseline Q1.
Question: do these retained owners still serve any final public observation?
Falsifier: snapshot, match observations, journal observations or counts change.
No production imports this file; remove/absorb after the measured verdict.
"""
import gc
import json
import subprocess
import os
import time
import tracemalloc
import weakref


def install(state):
    from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
    from moss_transcribe_diarize.app.live_service_runtime import LiveServiceRuntime
    original_run = LiveServiceRuntime._run_terminal
    original_journal = LiveCoordinator.journal_observations
    original_match = LiveCoordinator.match_observations
    def journal(self):
        if hasattr(self, '_prototype_journal'):
            return self._prototype_journal
        return original_journal(self)
    def match(self):
        if hasattr(self, '_prototype_match'):
            return self._prototype_match
        return original_match(self)
    LiveCoordinator.journal_observations = journal
    LiveCoordinator.match_observations = match
    def finalized(self, session, plan, tape):
        original_run(self, session, plan, tape)
        with self._lock:
            c = session.coordinator
            if session.session.snapshot().finalization_status != 'final':
                return
            before = self._snapshot(session).to_dict()
            observations = c.journal_observations()
            matches = c.match_observations()
            counts = c.identity_counts()
            old = [weakref.ref(p) for p in c._lane_preparers.values()]
            gc.collect()  # Exclude already-dead HTTP cycles from the release delta.
            traced_before = tracemalloc.get_traced_memory()[0]
            c._prototype_journal = observations
            c._prototype_match = matches
            c._lane_preparers.clear()
            gc.collect()
            traced_after = tracemalloc.get_traced_memory()[0]
            row = dict(time=time.monotonic(), session_id=session.session_id,
                traced_before=traced_before,traced_after=traced_after,
                preparers_before=len(old),preparers_alive_after=sum(r() is not None for r in old),
                snapshot_equal=before==self._snapshot(session).to_dict(),
                journal_equal=observations==c.journal_observations(),match_equal=matches==c.match_observations(),
                counts_equal=counts==c.identity_counts(),rss_bytes=int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())],text=True))*1024)
            with (state/'release-prototype.jsonl').open('a') as stream:
                stream.write(json.dumps(row)+'\n')
    LiveServiceRuntime._run_terminal = finalized
