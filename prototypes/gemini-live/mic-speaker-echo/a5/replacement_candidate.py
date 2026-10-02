"""Throwaway measured method substitution; product source is never edited here."""
import inspect
import textwrap

from moss_transcribe_diarize.app import gemini_live_runtime as rt

INVALIDATE = '''                    solid = session.snapshot().effective_transcript
                    removed = [row for row in snapshot.effective_transcript
                               if row.authority == "provisional" and row not in solid]
                    state.preview_cuts[:] = [
                        (lane, end, prefix) for lane, end, prefix in state.preview_cuts
                        if not any(row.source_lane == lane and row.start_sample < end
                                   for row in removed)]
'''


def runtime_class():
    source = inspect.getsource(rt.GeminiLiveRuntime.publish_update)
    marker = '                    kind = "text_revision_applied"\n'
    assert source.count(marker) == 1
    source = source.replace(marker, INVALIDATE + marker)
    scope = dict(rt.__dict__)
    # Preserve the existing frozen harness's module-level trim substitutions.
    scope["_trim_committed_preview"] = lambda *a, **k: rt._trim_committed_preview(*a, **k)
    exec(textwrap.dedent(source), scope)
    stop = inspect.getsource(rt.GeminiLiveRuntime._finish_stop)
    marker = '            self._record_event(state, "session_closed", {\n'
    assert stop.count(marker) == 1
    stop = stop.replace(marker, '            state.preview_cuts.clear()\n' + marker)
    exec(textwrap.dedent(stop), scope)
    return type("PrototypeRuntime", (rt.GeminiLiveRuntime,), {
        "publish_update": scope["publish_update"], "_finish_stop": scope["_finish_stop"]})
