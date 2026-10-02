"""Recorded-answer omission on the real >900s schedule/stitcher; timing placement is injected."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT),str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parent.parent/'f3')]
import f3lib
from moss_transcribe_diarize.app import gemini_coverage as candidate
from moss_transcribe_diarize.app import gemini_provider as provider
from moss_transcribe_diarize.app.gemini_long_final import LongFinalStitcher
from moss_transcribe_diarize.app.live_transcript_convergence import terminal_speaker_mapping
from moss_transcribe_diarize.app.gemini_coverage import WitnessWord, source_partitions
S=16000
EV=f3lib.EV.parent.parent/'R5B-C2'


def run():
    mode='product'
    original=json.loads((f3lib.EV/'runs/en-k3-p0-rule/terminal.json').read_text())['system']['before_rule']
    # Recorded provider word text/time/label, shifted intact to cross the870-900s seam.
    recorded=[provider.GeminiWord(text,label,a+880*S,b+880*S) for text,label,a,b in original]
    omitted=[w for w in recorded if w.speaker=='terminal-0002']
    assert omitted
    cleanup=[w for w in recorded if w not in omitted]
    live=[provider.GeminiWord(w.text,'published-'+w.speaker,w.start_sample,w.end_sample) for w in recorded]
    calls=[]
    class Decoder:
        def diarize(self,pcm,**kwargs):
            start=0 if len(pcm)//2==900*S else 870*S
            calls.append((start,len(pcm)//2))
            # Different request-local label namespace in second chunk.
            return provider.GeminiWords(tuple(provider.GeminiWord(w.text,('second-' if start else 'first-')+w.speaker,
                w.start_sample-start,w.end_sample-start) for w in cleanup if start<=w.start_sample<start+len(pcm)//2))
    class Encoder:
        def __init__(self):self.calls=0
        def embed_intervals(self,*args):self.calls+=1;return []
    class Tape:
        sample_count=930*S
        def read(self,*,start_sample=0,end_sample=None):return bytes(2*((self.sample_count if end_sample is None else end_sample)-start_sample))
    encoder=Encoder();terminal=provider.TerminalTranscriber(Decoder(),source_lane='system',stitcher=LongFinalStitcher(encoder))
    baseline=terminal.transcribe(Tape());baseline_calls=encoder.calls
    terminal.set_witness_words(live)
    rows=terminal.transcribe(Tape())
    final=terminal.last_words
    surface=[SimpleNamespace(start_sample=w.start_sample,end_sample=w.end_sample,canonical_speaker=w.speaker) for w in live]
    names=terminal_speaker_mapping(tuple((r.speaker,r.start_sample,r.end_sample,r.text) for r in rows),
        base_surface=surface,canonical_speakers=tuple(dict.fromkeys(w.speaker for w in live)))
    restored=[w for w in final if w.text in {w.text for w in omitted} and any(w.start_sample==o.start_sample and w.text==o.text for o in omitted)]
    assert len(restored)==len(omitted)
    assert {names[w.speaker] for w in restored}=={'published-terminal-0002'}
    assert encoder.calls==baseline_calls*2
    result={'mode':mode,'injection':'recorded en-k3 answer: remove entire middle-speaker utterance; shift880s; change chunk namespace',
        'samples':Tape.sample_count,'schedule':calls,'omitted_words':len(omitted),'restored_words':len(restored),
        'saved_live_names':sorted({names[w.speaker] for w in restored}),'encoder_calls_without_with':[baseline_calls,encoder.calls-baseline_calls],
        'final_labels':names,'rows':[{'text':r.text,'label':r.speaker,'live_name':names[r.speaker]} for r in rows]}
    # Stress cell2 export replay: real welcome text/name, injected word timings/omission.
    stress=EV.parent/'P73/r5b-stress/runs/c2'
    exported=json.loads((stress/'saved-meeting-live.json').read_text())['transcript']['segments']
    welcome=next(r for r in exported if r['source_lane']=='system' and r['text'].startswith('Welcome'))
    tokens=welcome['text'].split()
    n=len(tokens)
    spoken=tuple(provider.GeminiWord(text,welcome['speaker_entity_id'],
        round((welcome['start']+(welcome['end']-welcome['start'])*i/n)*S),
        round((welcome['start']+(welcome['end']-welcome['start'])*(i+1)/n)*S)) for i,text in enumerate(tokens))
    own=provider.GeminiWord('No.',welcome['speaker_entity_id'],round(26.1*S),round(26.3*S))
    singer=provider.GeminiWord('truth?','speaker-0004',60*S,round(60.3*S))
    david=provider.GeminiWord('David.','speaker-0003',round(68.2*S),round(69.2*S))
    class Cell2Decoder:
        def diarize(self,*args,**kwargs):
            return provider.GeminiWords(tuple(provider.GeminiWord(w.text,'clean-'+w.speaker,w.start_sample,w.end_sample)
                for w in (own,singer,david)))
    cell2=provider.TerminalTranscriber(Cell2Decoder(),source_lane='system')
    cell2.set_witness_words((own,singer)+spoken+(david,))
    cell2_rows=cell2.transcribe(Tape())
    names2=terminal_speaker_mapping(tuple((r.speaker,r.start_sample,r.end_sample,r.text) for r in cell2_rows),
        base_surface=tuple(SimpleNamespace(start_sample=w.start_sample,end_sample=w.end_sample,canonical_speaker=w.speaker)
            for w in (own,singer)+spoken+(david,)),canonical_speakers=('speaker-0002','speaker-0003','speaker-0004'))
    restored2=[w for w in cell2.last_words if welcome['start']*S<=w.start_sample<welcome['end']*S]
    assert len(restored2)==n and {names2[w.speaker] for w in restored2}=={welcome['speaker_entity_id']}
    result['cell2_export_injection']={'text':welcome['text'],'live_span':[welcome['start'],welcome['end']],
        'words':n,'saved_words':len(restored2),'live_id':welcome['speaker_entity_id'],'live_name':welcome['speaker'],
        'saved_id':names2[restored2[0].speaker],
        'limits':'recorded exported text/name; word times evenly interpolated within live row; clean-up omission injected, not original provider replay'}
    # Correspondence ambiguity controls: split never pools; merge never joins old groups; no matching words means new partition.
    old=[WitnessWord('a','same',S,S+3200,'pA'),WitnessWord('b','same',2*S,2*S+3200,'pB')]
    words=[provider.GeminiWord(w.text,'merged',w.start_sample,w.end_sample) for w in old]
    updated,mapping,context=source_partitions(old,old,words,3*S)
    assert [w.source_partition for w in updated]==['pA','pB'] and mapping['merged'] not in ('pA','pB')
    old=[WitnessWord(w.text,w.speaker,w.start_sample,w.end_sample,'pBoth') for w in old]
    words=[provider.GeminiWord(w.text,'split-'+w.text,w.start_sample,w.end_sample) for w in old]
    updated,mapping,_=source_partitions(old,old,words,3*S)
    assert len({w.source_partition for w in updated})==2
    _,mapping,_=source_partitions(old,old,[provider.GeminiWord('unmatched','same',4*S,4*S+3200)],5*S)
    assert mapping['same']!='pBoth'
    result['ambiguities']='merge separate; split positive old matches into distinct new groups; no match new'
    EV.mkdir(exist_ok=True);(EV/(mode+'-extended.json')).write_text(json.dumps(result,indent=1)+'\n')
    print(json.dumps(result,indent=1))

if __name__=='__main__':run()
