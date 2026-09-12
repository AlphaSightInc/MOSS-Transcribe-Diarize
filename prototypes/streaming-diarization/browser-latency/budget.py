"""Content-free timing budget from measured frames and the production lane mixer."""
import argparse,json,sys,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tests.test_live_mixer import _Runtime,_frame
from moss_transcribe_diarize.app.live_lane_contract import LiveLane
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session
from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixer

def budget(path,known=None):
 rows=json.loads((path/'timings.json').read_text());align=json.loads((path/'alignment.json').read_text())
 click=next(r['t'] for r in rows if r['kind']=='start_click');dom=next(r['t'] for r in rows if r['kind']=='dom')
 text=next(r for r in rows if r['kind']=='json' and r['t']>=click and ((r.get('provisional') or {}).get('words') or r.get('effective') or r.get('draft')))
 signal=next(r['t'] for r in rows if r['kind']=='signal' and r.get('items'))
 events={e['seq']:e for r in rows for e in (r.get('events') or [])}
 first=next(e['payload'] for e in events.values() if e['kind']=='canonical_processed' and e['payload']['span_id']==0)
 requests=[r for r in rows if r['kind']=='request' and r.get('frame')]
 rtts=[];worklets={};encoding=[]
 for r in rows:
  if r['kind']=='worklet' and r.get('session'):worklets[(r['lane'],r['startFrame'])]=r
  if r['kind']=='encoded':encoding.append(r['elapsed'])
  if r['kind']=='response' and r.get('frame'):rtts.append(r['elapsed'])
 # Replay timing-only frame headers through the real mixer. PCM values do not affect its frontier.
 source=LiveV2Session(max_retained_samples=16000000);runtime=_Runtime();mixer=LiveCompatibilityMixer(max_output_samples=16000);mix=[]
 for r in requests:
  f=r['frame'];source.accept(_frame(LiveLane(f['lane']),f['sequence'],f['timestamp_ns'],16000,f['samples'],0,silent=True))
  result=mixer.admit_available('budget',source,runtime)
  if result:mix.append({'t':r['t'],'end_ns':result.diagnostics.end_timestamp_ns,'samples':result.frame.sample_count})
 poll=[r['t'] for r in rows if r['kind']=='request' and r.get('path','').endswith('/snapshot') and click<=r['t']<=dom]
 result=dict(click_to_dom_ms=round(dom-click,3),row4_first_visible_seconds=json.loads((path/'row-04.json').read_text())['first_visible_seconds'],
  first_text_snapshot_from_click_ms=round(text['t']-click,3),snapshot_to_signal_ms=round(signal-text['t'],3),signal_to_dom_ms=round(dom-signal,3),
  frame_samples=8000,frame_duration_ms=500,encoding_ms_p50=statistics.median(encoding),frame_http_ms_p50=statistics.median(rtts),
  polling_interval_ms_p50=statistics.median(b-a for a,b in zip(poll,poll[1:])),first_canonical_decode_ms=first['canonical_decode_elapsed_sec']*1000,
  first_canonical_queue_ms=first['queue_wait_ms'],canonical_spans=[e['payload'] for e in events.values() if e['kind']=='canonical_processed'],first_lane_batches_from_click_ms={lane:next(r['t']-click for r in worklets.values() if r['lane']==lane) for lane in ('microphone','system')},
  first_mixed_admission_from_click_ms=mix[0]['t']-click,known_onset=[])
 if known is not None:
  speech_dom=next((r['t'] for r in rows if r['kind']=='known_speech_dom'),None)
  result['known_speech_to_dom_measured']=speech_dom is not None
  for lane in ('microphone','system'):
   a=next(a for a in align if a['lane']==lane and a['file_offset_samples']>=round(known*16000) and a['correlation']>.95)
   f=worklets[(lane,a['startFrame'])];onset_frame=a['startFrame']+round(known*16000)-a['file_offset_samples']
   onset=f['t']+1000*(onset_frame/16000-f['contextTime'])
   containing=next(v for v in worklets.values() if v['lane']==lane and v['startFrame']<=onset_frame<v['startFrame']+8000)
   delivered=next(r for r in requests if r['frame']['lane']==lane and r['frame']['timestamp_ns']==round(containing['startFrame']/16000*1e9))
   sealed=next(m for m in mix if m['end_ns']>round(onset_frame/16000*1e9))
   result['known_onset'].append(dict(lane=lane,correlation=a['correlation'],onset_from_click_ms=round(onset-click,3),
    onset_to_worklet_ms=round(containing['t']-onset,3),worklet_to_upload_ms=round(delivered['t']-containing['t'],3),
    upload_to_mixed_frontier_ms=round(sealed['t']-delivered['t'],3),onset_to_any_text_dom_ms=round(dom-onset,3),onset_to_matching_speech_dom_ms=None if speech_dom is None else round(speech_dom-onset,3)))
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--known-onset',type=float);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 r=budget(a.directory,a.known_onset);a.out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
