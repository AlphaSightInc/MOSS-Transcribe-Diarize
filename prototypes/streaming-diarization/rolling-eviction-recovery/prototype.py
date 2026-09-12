"""One-command before/after experiment; patch a disposable module, never repo source."""
import json, sys, types, subprocess
from pathlib import Path
from dataclasses import dataclass
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape
from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app import live_transcript_convergence as original

def candidate_source(source):
    source=source.replace('from typing import Any, Mapping, Protocol, Sequence','from typing import Any, Callable, Mapping, Protocol, Sequence')
    source=source.replace('geometry: RollingGeometry = DEFAULT_ROLLING_GEOMETRY,\n    ):','geometry: RollingGeometry = DEFAULT_ROLLING_GEOMETRY,\n        pcm_reader: Callable[..., bytes] | None = None,\n    ):',1)
    source=source.replace('self.geometry = geometry\n','self.geometry = geometry\n        self._pcm_reader = pcm_reader\n',1)
    a='''        if start_sample < self._buffer_start_sample:
            self._status = RollingStatus.PCM_EVICTED
            return ()

        offset = (start_sample - self._buffer_start_sample) * PCM16_BYTES_PER_SAMPLE
        payload = bytes(
            self._buffer[offset : offset + self.geometry.window_samples * PCM16_BYTES_PER_SAMPLE]
        )'''
    b='''        if start_sample < self._buffer_start_sample:
            if self._pcm_reader is None:
                self._end_refinement(RollingStatus.PCM_EVICTED)
                return ()
            try:
                payload = self._pcm_reader(start_sample=start_sample, end_sample=end_sample)
            except CompleteMixedTapeUnavailable:
                self._end_refinement(RollingStatus.PCM_EVICTED)
                return ()
            if len(payload) != self.geometry.window_samples * PCM16_BYTES_PER_SAMPLE:
                self._end_refinement(RollingStatus.PCM_EVICTED)
                return ()
        else:
            offset = (start_sample - self._buffer_start_sample) * PCM16_BYTES_PER_SAMPLE
            payload = bytes(
                self._buffer[offset : offset + self.geometry.window_samples * PCM16_BYTES_PER_SAMPLE]
            )'''
    assert a in source;source=source.replace(a,b,1)
    source=source.replace('if self._status is RollingStatus.ROLLING:\n                self._end_refinement(RollingStatus.PCM_EVICTED)','if self._status is RollingStatus.ROLLING and self._pcm_reader is None:\n                self._end_refinement(RollingStatus.PCM_EVICTED)',1)
    return source

@dataclass
class Surface:
    committed_samples:int
    canonical_through_sample:int=0
    text_revision_version:int=0
    epoch:int=0

def measure(cls, recovery):
    tape=CompleteMixedTape(epoch=0,capacity_bytes=16000*2*60)
    reads=[]
    def read(**kw):reads.append(kw);return tape.read(**kw)
    c=cls(epoch=0,**({'pcm_reader':read} if recovery else {}));payload=b''
    # Request first 10 s only after canonical work catches up at 17.5 s.
    for frame in range(35):
        pcm=frame.to_bytes(2,'little')*8000;payload+=pcm
        tape.append(start_sample=frame*8000,pcm=pcm);c.accept_pcm(frame*8000,pcm)
    request=c.observe_base(Surface(160000))[0]
    for frame in range(35,68): # another 16.5 s of capture while the request waits
        pcm=frame.to_bytes(2,'little')*8000;payload+=pcm
        tape.append(start_sample=frame*8000,pcm=pcm);c.accept_pcm(frame*8000,pcm)
    before=c.accounting();ends=[]
    while c.accounting().status.value == 'rolling':
        assert request.pcm==payload[request.start_sample*2:request.end_sample*2]
        proposal=c.complete(request.id,InferenceTranscript('[0][S01]hello[10]',elapsed_sec=.1))
        if proposal is None:break
        ends.append(proposal.end_sample)
        requests=c.observe_base(Surface(68*8000,proposal.end_sample,len(ends)))
        if not requests:break
        request=requests[0]
    return {'status_after_wait':before.status.value,'status_after_drain':c.accounting().status.value,
            'planned':c.accounting().windows_planned,'applied_ends':ends,'tape_reads':reads,
            'ring_peak_samples':c.accounting().retained_high_water_samples,'ring_limit_samples':c.geometry.max_retained_samples}

if __name__=='__main__':
    name='moss_transcribe_diarize.app._eviction_prototype';m=types.ModuleType(name);sys.modules[name]=m
    exec(compile(candidate_source(subprocess.check_output(["git", "show", "323f1222:moss_transcribe_diarize/app/live_transcript_convergence.py"], cwd=ROOT, text=True)),'<prototype>','exec'),m.__dict__)
    result={'baseline':measure(original.RollingTranscriptConverger,False),'candidate':measure(m.RollingTranscriptConverger,True)}
    assert result['baseline']['status_after_wait']=='pcm_evicted'
    assert result['candidate']['applied_ends']==[160000,320000,480000]
    assert result['candidate']['ring_peak_samples']<=320000
    print(json.dumps(result,indent=2))
