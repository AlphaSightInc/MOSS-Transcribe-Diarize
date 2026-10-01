"""F2's 28 recorded round-4 samples through production gates + BC restoration; source evidence read-only."""
import importlib.util
import json
from pathlib import Path
import soundfile as sf

import compose
from compose import candidate, S
import fixtures
import ledger
import provider as recorded_provider
from moss_transcribe_diarize.app.gemini_provider import GeminiWord

EV=Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/P72/bc'
F2EV=EV.parent/'f2'
spec=importlib.util.spec_from_file_location('bc_r4_chain',compose.F2/'r4_chain.py')
chain=importlib.util.module_from_spec(spec)
spec.loader.exec_module(chain)


def run():
    # Source builders must not write into the adjacent worktree. All required files were built by F2 already.
    for marker in (fixtures.QMIC/'reference.json',fixtures.MH/'fixture/reference.json',fixtures.MH/'fixture2/reference.json',
                   fixtures.FIX/'r4-A-listen-mic.wav',fixtures.FIX/'r4-B-listen-mic.wav'):
        assert marker.is_file(),f'UNMEASURED missing read-only fixture: {marker}'
    lanes=fixtures.r4_lanes()
    rows=[]
    for sample in sorted((F2EV/'runs/r4-final').glob('*.json')):
        if sample.name=='summary.json':continue
        original=json.loads(sample.read_text())
        name=original['lane']
        mic_path,tab_path,_=lanes[name]
        mic=sf.read(mic_path,dtype='int16')[0]
        tab=sf.read(tab_path,dtype='int16')[0]
        captured=[]
        original_terminal=candidate.filter_terminal
        original_live=candidate.filter_live
        def terminal(gate,pcm,words,system,*,system_pcm16=None):
            captured.extend(words)
            return original_terminal(gate,pcm,words,system,system_pcm16=system_pcm16)
        def live(gate,pcm,words,*,offset_sample=0):
            captured.extend(gate.webrtc_gate.filter(pcm,words,offset_sample=offset_sample))
            return original_live(gate,pcm,words,offset_sample=offset_sample)
        candidate.filter_terminal=terminal
        candidate.filter_live=live
        try:
            if original['pass']=='saved':
                measured=chain.terminal(name,mic,tab,False)
                pcm,tab_pcm=mic.tobytes(),tab.tobytes()
                witnesses=tuple(captured)
            else:
                start,end=original['window_s']
                measured=chain.windows(name,mic,tab,[end],False)[0]
                pcm,tab_pcm=mic[start*S:end*S].tobytes(),tab[start*S:end*S].tobytes()
                witnesses=tuple(GeminiWord(w.text,w.speaker,w.start_sample-start*S,w.end_sample-start*S) for w in captured)
        finally:
            candidate.filter_terminal=original_terminal
            candidate.filter_live=original_live
        actual=measured.get('candidate_saved_words',measured.get('candidate_published_words',[]))
        assert actual==original.get('candidate_saved_words',original.get('candidate_published_words',[])),sample.name
        for w_on in (False,True):
            system,state=compose.w_labels((),tab_pcm,chain.encoder(),enabled=w_on)
            for anchored in (False,True):
                compose.LOG.clear()
                gate=chain.gate(tab_pcm)
                gate.local_speech_seen=anchored
                output,restored=compose.mic_restore(gate,pcm,(),witnesses,system,tab_pcm)
                row={'sample':sample.stem,'w':w_on,'anchored':anchored,'provider_words':len(witnesses),
                     'f2_kept':len(actual),'bc_restored':len(output),'state':list(compose.LOG)}
                rows.append(row)
                assert not output,row
        print(json.dumps({'sample':sample.stem,'provider_words':len(witnesses),'f2_kept':len(actual),'bc_restored':0}),flush=True)
        (EV/'negative-matrix.json').write_text(json.dumps(rows,ensure_ascii=False,indent=1)+'\n')
    assert len(rows)==28*4,len(rows)
    print(json.dumps({'samples':28,'provider_words':sum(r['provider_words'] for r in rows if not r['w'] and not r['anchored']),
                      'bc_restored':sum(r['bc_restored'] for r in rows),'conditions':len(rows)}),flush=True)

if __name__=='__main__':run()
