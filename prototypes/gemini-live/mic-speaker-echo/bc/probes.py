"""A/B failure probes, production terminal + microphone gates, deterministic public audio/timed-word injections."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import soundfile as sf

import compose
from compose import candidate, evidence, rule, S
from moss_transcribe_diarize.app.gemini_final_policy import WebRtcWordGate
from moss_transcribe_diarize.app.gemini_hybrid_engine import WeSpeakerWindowEmbeddings
from moss_transcribe_diarize.app.gemini_lane_engine import AcousticEchoGuard, CrossLaneVoiceEchoGuard, MicrophoneWordGate, SystemWordLedger
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
from moss_transcribe_diarize.app.gemini_provider import GeminiWord

EV = Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/P72/bc'
RD = EV.parent/'mic-speaker-echo'
F3EV = EV.parent/'f3'
ENCODER = None


def word(text, a, b, label='echo'):
    return GeminiWord(text, label, round(a*S), round(b*S))


def gate(tab, system=(), anchored=False):
    global ENCODER
    if ENCODER is None:
        ENCODER = _identity_encoder(LiveProviderBundleConfig.from_manifest(compose.w_rule.MANIFEST), interval_workers=3)
    ledger = SystemWordLedger()
    ledger.observe(system, len(tab)//2)
    voice = CrossLaneVoiceEchoGuard(threshold=.60)
    voice.observe_system((), {}, frontier=len(tab)//2)
    result = MicrophoneWordGate(WebRtcWordGate(), ledger, AcousticEchoGuard(lambda a,b: tab[2*a:2*b]), None,
                               voice_guard=voice, embedding_source=WeSpeakerWindowEmbeddings(ENCODER))
    result.local_speech_seen = anchored
    return result


def a_audio(below):
    """Public phrase audio already used by F2; no adjacent worktree writes."""
    import fixtures
    tab = fixtures.system()
    speech, _ = fixtures.local([(5.0, 96.0, 97.1)], -17.0-below)
    mic = fixtures.floor()+fixtures.d_build.echo_of(tab, -40.0)+speech
    return fixtures.pcm(mic).tobytes(), fixtures.pcm(tab).tobytes()


def run():
    rows=[]
    for below in (10,20):
        pcm, tab = a_audio(below)
        flags = candidate.local_audio(pcm, tab, whole_lane=True)
        # Six timestamp witnesses in the public 1.1s phrase: constructed reviewer denominator, not a new ASR draw.
        local = [word(t, 5.3+i*.13, 5.3+(i+1)*.13, 'local-live')
                 for i,t in enumerate(['Can','you','elaborate','on','that','please?'])]
        before=[word(f'echo{i}', 3.2+i*.40, 3.2+i*.40+.10) for i in range(5)]
        after=[word(f'tab{i}', 6.65+i*.40, 6.65+i*.40+.10) for i in range(20)]
        cleanup=before+after
        naive, _ = rule.fill_holes(cleanup, local)
        voiced=gate(tab).webrtc_gate.filter(pcm, naive)
        eligible, stretches, runs = candidate.local_words(flags, voiced, 0)
        print(json.dumps({'probe':'naive','below_tab_db':below,'words':len(voiced),'eligible':len(eligible),
                          'runs':runs,'stretches':candidate._spans(stretches)},ensure_ascii=False),flush=True)
        assert len(voiced)==31 and len(eligible)==0 and runs[0]['on_unexplained']==6, runs
        for w_on in (False,True):
            # W acts on the tab only. Its actual Engine is executed, not a label-renaming stand-in.
            tab_words, w_state = compose.w_labels(cleanup, tab, ENCODER, enabled=w_on)
            compose.LOG.clear()
            output, restored=compose.mic_restore(gate(tab, tab_words), pcm, cleanup, local, tab_words, tab)
            saved=[w for w in output if w.text in {p.text for p in local}]
            result={'probe':'isolated','below_tab_db':below,'w':w_on,'saved':len(saved),'wanted':6,
                    'restored':restored,'state':list(compose.LOG),'w_state':w_state}
            rows.append(result)
            print(json.dumps(result,ensure_ascii=False),flush=True)
            assert len(saved)==6, result
            # Supported 3–5-word candidates and withheld one-/two-word candidates on the same measured stretch.
            for count in (1,2,3,4,5):
                compose.LOG.clear()
                output, restored=compose.mic_restore(gate(tab,tab_words),pcm,cleanup,local[:count],tab_words,tab)
                got=sum(w.text in {p.text for p in local[:count]} for w in output)
                rows.append({'probe':'reply-length','below_tab_db':below,'w':w_on,'words':count,'saved':got,
                             'state':list(compose.LOG)})
                assert got==(count if count>=3 else 0), rows[-1]
    # Round-4 pattern injection: three separate invented characters beside a genuine local turn.
    pcm=sf.read(F3EV/'fixtures/mic-events.wav',dtype='int16')[0].tobytes()
    tab=sf.read(F3EV/'fixtures/sys-60.wav',dtype='int16')[0].tobytes()
    recorded = json.loads((F3EV/'runs/inv-events-rule/terminal.json').read_text())
    truth_words = [GeminiWord(*w) for w in recorded['microphone']['before_rule'] if 9*S <= w[2] < 15*S]
    tab_recorded = [GeminiWord(*w) for w in recorded['system']['before_rule']]
    attacks={
        'round4-pattern':[word('是。',16.5,16.8,'real'),word('哦。',17.5,17.8,'real'),word('六。',18.5,18.8,'real')],
        'noise-three-words':[word(t,22+i*.2,22+(i+1)*.2,'real') for i,t in enumerate(['Think','about','this'])],
        'noise-long-run':[word(t,45+i*.3,45+(i+1)*.3,'real') for i,t in enumerate(['Could','you','say','that','again'])],
    }
    for w_on in (False,True):
        system,w_state=compose.w_labels(tab_recorded,tab,ENCODER,enabled=w_on)
        for anchored in (False,True):
            for name,attack in attacks.items():
                compose.LOG.clear()
                g=gate(tab,system,anchored)
                before=g.local_speech_seen
                output,restored=compose.mic_restore(g,pcm,truth_words,truth_words+attack,system,tab)
                result={'probe':name,'w':w_on,'anchored_before':before,'anchored_after':g.local_speech_seen,
                        'restored_words':sum(len(r['text']) for r in restored),'state':list(compose.LOG),
                        'cleanup_words_kept':len(output),'w_state':w_state}
                rows.append(result)
                print(json.dumps(result,ensure_ascii=False),flush=True)
                assert result['restored_words']==0 and result['cleanup_words_kept']>0 and result['anchored_after'], result
    EV.mkdir(parents=True,exist_ok=True)
    (EV/'probes.json').write_text(json.dumps(rows,ensure_ascii=False,indent=1)+'\n')
    return rows

if __name__=='__main__':
    run()
