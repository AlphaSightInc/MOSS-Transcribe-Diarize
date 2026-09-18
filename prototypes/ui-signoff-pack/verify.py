"""Compare fresh /new regeneration with the frozen owner checklist, not nondeterministic pixels."""
import json,socket,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'evidence/mvpfix/wp24'
def main():
    target=Path(sys.argv[1]);pack=target/'pack'
    assert (BASE/'pack/index.md').read_bytes()==(pack/'index.md').read_bytes(),'Checklist changed'
    data=json.loads((pack/'pack.json').read_text());rows=data['captures']
    states={r['state'] for r in rows};assert len(rows)==156 and len(states)==52
    assert all({r['viewport']['width'] for r in rows if r['state']==state}=={1440,1280,400} for state in states)
    assert all(not r['horizontal_scroll'] and not r['missing_accessible_names'] and not r['geometric_overlaps'] for r in rows)
    assert all(c['result']!='fail' for r in rows for c in r['contrast'])
    assert all((pack/r['screenshot']).is_file() and (pack/Path(r['screenshot']).with_suffix('.txt')).is_file() for r in rows)
    for state in ['active-two-lanes','browser-active-overlap']:
        for row in [r for r in rows if r['state']==state]:
            assert {'System','Microphone'} <= {r['lane'] for r in row['transcript_rows']}
    assert all(any(t['state']=='provisional' for t in r['transcript_rows']) for r in rows if r['state']=='provisional-rows')
    assert all(r['focus_restored_to_trigger'] for r in json.loads((target/'keyboard.json').read_text()))
    counts=json.loads((target/'request-count.json').read_text());assert counts['wp24_cumulative']<=150
    for port in [18124,17884,17885,17886]:
        with socket.socket() as s:
            s.settimeout(.3);assert s.connect_ex(('127.0.0.1',port))!=0,('Owned listener still running',port)
    report=dict(passed=True,checklist_equal=True,states=52,viewports=3,captures=156,horizontal_overflow=0,unnamed_controls=0,measured_contrast_failures=0,header_panel_overlaps=0,keyboard_focus_restoration='3/3',requests=counts,owned_listeners_remaining=0)
    (target/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
