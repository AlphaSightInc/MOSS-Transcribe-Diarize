"""Public recorded events through PRODUCT hybrid -> lanes -> runtime, vs measured reducer."""
import ast
import inspect
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT),str(HERE),str(HERE.parent/'f1')]
import candidate
import score
import stream
from measure_core import snapshot_state
from moss_transcribe_diarize.app import gemini_live_runtime as rt
from moss_transcribe_diarize.app.gemini_hybrid_engine import GeminiHybridEngine, FixedWindowScheduler, OverlapRegistry
from moss_transcribe_diarize.app.gemini_lane_engine import LaneGeminiEngine
from moss_transcribe_diarize.app import gemini_hybrid_engine as hybrid_module, gemini_lane_engine as lane_module
from moss_transcribe_diarize.app.live_session import AudioFrame

EV=Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-A4'
S=16000


class Idle:
    def __init__(self,publish=None):pass
    def close(self):pass
    def words(self,*args,**kwargs):return ()


def baseline_class(module, class_name, method_name):
    # Exact pre-A4 methods on current primitives; no text-rule changes.
    source=subprocess.run(['git','show',f'41bc82d9:moss_transcribe_diarize/app/{module.__name__.split(".")[-1]}.py'],
                          cwd=ROOT,capture_output=True,text=True,check=True).stdout
    tree=ast.parse(source)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==method_name)
    code=ast.get_source_segment(source,method)
    scope=dict(module.__dict__)
    exec(code,scope)
    return type('PreA4'+class_name,(getattr(module,class_name),),{method_name:scope[method_name]})


def replay(name,loader,runtime_type,verify=False,
           hybrid_type=GeminiHybridEngine,lane_type=LaneGeminiEngine):
    events,commits,total=loader()
    events=sorted(events,key=lambda e:e[2])
    pending=list(commits)
    expected=candidate.PreviewSnapshots()
    times,trace,pipeline_times=[],[],[]
    changed=extra=parity=safety=0
    with tempfile.TemporaryDirectory() as tmp:
        runtime=runtime_type(descriptor=stream.descriptor(total//S+1),tape_storage_root=tmp,
            engine_factory=lambda _id,publish,_usage:rt.ScriptedGeminiEngine(publish,batches=(),terminal=()))
        runtime.create(session_id='one')
        def publish(update):
            nonlocal changed,extra,parity,safety
            if not isinstance(update,rt.GeminiPreview):
                runtime.publish_update('one',update)
                if verify:
                    expected.advance(runtime.snapshot('one').session.effective_transcript)
                return
            if update.finished_turns and not update.segments and not update.lane_end_samples:
                runtime.publish_update('one',update)
                if verify:
                    expected.finish(update.finished_turns)
                return
            if verify:
                solid=runtime.snapshot('one').session.effective_transcript
                text=rt._trim_committed_preview(update.segments,solid,list(runtime._sessions['one'].preview_cuts))
                expected.advance(solid)
                expected.publication(update.origins,update.lane_end_samples,update.finished_turns)
                time_cuts=expected.cuts(update.segments,update.origins)
                wanted=candidate.apply_time_cuts(update.segments,text,time_cuts)
                expected.finish(update.finished_turns)
            before=time.perf_counter()
            runtime.publish_update('one',update)
            times.append((time.perf_counter()-before)*1000)
            if verify:
                provisional=runtime.snapshot('one').session.provisional
                actual=[r['text'] for r in provisional.segments]
                assert actual==[r.text for r in wanted],(name,len(trace),actual,wanted)
                assert snapshot_state(runtime._sessions['one'].preview_snapshots)==snapshot_state(expected)
                bc=score.cuts(update.segments,text)
                oc=score.cuts(update.segments,wanted)
                for (_,raw,b),(_,_,chosen),tc in zip(bc,oc,time_cuts):
                    safety+=max(0,chosen-max(b,tc))
                    parity+=int(tc<=b and chosen!=b)
                    extra+=chosen-b
                changed+=wanted!=text
                trace.append(dict(publication=len(trace),lane_clocks=update.lane_end_samples,
                    raw=[r.text for r in update.segments],text_only=[r.text for r in text],
                    shown=actual,time_cuts=time_cuts,state=snapshot_state(expected),
                    diagnostics=runtime.engine_diagnostics('one')['preview']))
        lanes=lane_type(publish,system_factory=Idle,microphone_factory=Idle,tape_root=Path(tmp))
        hybrid=hybrid_type(lambda u:lanes._on_update('system',u),word_source=Idle(),
            window_scheduler=FixedWindowScheduler(),registry=OverlapRegistry(),diarizer=Idle(),
            terminal=Idle(),source_lane='system')
        at=0
        try:
            for seq,start in enumerate(range(0,total-8000+1,8000)):
                accepted=start+8000
                runtime.accept_frame('one',AudioFrame(seq,b'\0'*16000,8000))
                hybrid._accepted=accepted
                while pending and accepted>=pending[0][1]+round(3.5*S):
                    old,frontier,rows=pending.pop(0)
                    lanes._on_update('system',rt.GeminiRolling(old,frontier,rows))
                    lanes._on_update('microphone',rt.GeminiRolling(old,frontier,()))
                    hybrid._committed=frontier
                while at<len(events) and events[at][2]<=accepted:
                    text,begin,end,final=events[at];at+=1
                    before_event=time.perf_counter()
                    hybrid._on_live_text(text,begin,end,final)
                    pipeline_times.append((time.perf_counter()-before_event)*1000)
            diagnostics=runtime.engine_diagnostics('one')['preview']
        finally:
            hybrid.close();lanes.close()
    if verify:
        (EV/f'{name}-pipeline.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')
    return dict(publications=len(times),changed_calls=changed,extra_removed_unit_publications=extra,
                time_outside_snapshot=safety,same_gate_mismatches=parity,
                mean_publication_ms=statistics.fmean(times),max_publication_ms=max(times),
                mean_source_to_publication_ms=statistics.fmean(pipeline_times),
                diagnostics=diagnostics)


def main():
    report={}
    baseline=baseline_class(rt,'GeminiLiveRuntime','publish_update')
    old_hybrid=baseline_class(hybrid_module,'GeminiHybridEngine','_on_live_text')
    old_lanes=baseline_class(lane_module,'LaneGeminiEngine','_on_update')
    for name,loader in [('zh-188s',stream.load_zh),('en-302s',stream.load_e1),('r5d-cell',stream.load_cell)]:
        before=replay(name,loader,baseline,hybrid_type=old_hybrid,lane_type=old_lanes)
        timed=replay(name,loader,rt.GeminiLiveRuntime)
        after=replay(name,loader,rt.GeminiLiveRuntime,verify=True)
        assert before['publications']==after['publications']
        added=timed['mean_source_to_publication_ms']-before['mean_source_to_publication_ms']
        assert added<=1,(name,added)
        assert after['time_outside_snapshot']==0 and after['same_gate_mismatches']==0
        report[name]=dict(baseline=before,product=after,timed_product=timed,added_mean_ms=added)
    (EV/'pipeline-product-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
