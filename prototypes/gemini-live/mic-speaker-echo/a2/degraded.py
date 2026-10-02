"""Replay c5b degraded rows through real publication; override ONLY trim/commit placement for prototype."""
import json,sys,tempfile
from dataclasses import replace
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'f1')]
import candidate,stream
rt=candidate.rt
from moss_transcribe_diarize.app.live_session import AudioFrame
ROOT=Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence'
EV=ROOT/'P73/a2'
S=16000

def run(product=False, baseline=False):
    original_trim=rt._trim_committed_preview
    cuts=candidate.RememberedTrim()
    cls=rt.GeminiLiveRuntime
    if baseline:
        rt._trim_committed_preview=lambda segs,committed,*args,degraded=False: tuple(segs) if degraded else original_trim(segs,committed)
    elif not product:
        rt._trim_committed_preview=lambda segs,committed,*args,degraded=False: cuts.trim(segs,committed,degraded=degraded)
    snaps=[json.loads(x) for x in (ROOT/'P73/r5b-stress/runs/c5b/snapshots.jsonl').read_text().splitlines()]
    eff=[];previous=0;commits=[];states=[]
    with tempfile.TemporaryDirectory() as tmp:
        desc=stream.descriptor(200)
        desc=replace(desc,bounds=replace(desc.bounds,max_retained_samples=200*S))
        runtime=cls(descriptor=desc,tape_storage_root=tmp,engine_factory=lambda _id,p,u:rt.ScriptedGeminiEngine(p,batches=(),terminal=()))
        runtime.create(session_id='one')
        for seq in range(200):runtime.accept_frame('one',AudioFrame(seq,b'\0'*32000,S))
        for snap in snaps:
            if snap.get('effective') is not None:eff=snap['effective']
            if snap['e']<70 or snap['e']>186:continue
            frontier=snap['committed']
            if not previous:
                runtime.publish_update('one',rt.GeminiBase(frontier,()))
                runtime.publish_update('one',rt.GeminiRolling(0,frontier,tuple(rt.GeminiSegment(r['start_sample'],r['end_sample'],r['text'],r['canonical_speaker'],r.get('source_lane')) for r in eff),revision_lanes=('system','microphone')))
            elif frontier>previous:
                rows=tuple(rt.GeminiSegment(r['start_sample'],r['end_sample'],r['text'],source_lane=r.get('source_lane')) for r in eff if r['authority']=='provisional' and r['start_sample']>=previous)
                before=len(runtime.snapshot('one').session.effective_transcript)
                runtime.publish_update('one',rt.GeminiBase(frontier,rows,degraded=True))
                commits.extend(r.text for r in runtime.snapshot('one').session.effective_transcript[before:])
            previous=frontier
            if snap.get('provisional'):
                p=snap['provisional'];runtime.publish_update('one',rt.GeminiPreview(p['end_sample'],tuple(rt.GeminiSegment(r['start_sample'],r['end_sample'],r['text'],source_lane=r.get('source_lane')) for r in p['segments'])))
            states.append({'e':snap['e'],'cuts':cuts.cuts,'solid':[(r.source_lane,r.text) for r in runtime.snapshot('one').session.effective_transcript]})
    from collections import Counter
    count=Counter(commits)
    rt._trim_committed_preview=original_trim
    head='大家好今天我们主要讨论一下第三季度的产品规划'
    normalized=lambda text: ''.join(u for u,_,_ in rt._preview_units(text))
    paragraph_heads=sum(head in normalized(text) for text in commits)
    return dict(commits=len(commits),right=count.get('right',0),paragraph_heads=paragraph_heads,max_duplicate=max(count.values(),default=0),duplicates={k:v for k,v in count.items() if v>1}),states
if __name__=='__main__':
    report={}
    for mode in ('baseline','prototype'):
        stat,states=run(baseline=mode=='baseline');report[mode]=stat
        (EV/f'degraded-{mode}.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in states))
    (EV/'degraded.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
