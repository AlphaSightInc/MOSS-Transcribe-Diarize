"""Throwaway BC composition; imports measured F2/H/W rules unchanged, no production writes."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
F2 = ROOT.parent / 'MOSS-Transcribe-Diarize-wt-r5-f2/prototypes/gemini-live/mic-speaker-echo/f2'
F3 = HERE.parent / 'f3'
W = ROOT.parent / 'MOSS-Transcribe-Diarize-wt-r5-p3/prototypes/gemini-live/label-purity/w/run.py'
sys.path[:0] = [str(ROOT), str(F2), str(F3)]
import candidate
import evidence
import rule
from moss_transcribe_diarize.app.gemini_provider import GeminiWord

spec = importlib.util.spec_from_file_location('bc_rule_w', W)
w_rule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w_rule)
S = 16000
LOG = []


def mic_restore(gate, pcm, cleanup, witness, system_words, system_pcm, *, skip=(), raw_cleanup=None):
    """Gate cleanup unchanged; judge each H candidate in isolation, then assign a label."""
    kept = list(candidate.filter_terminal(gate, pcm, cleanup, system_words, system_pcm16=system_pcm))
    flags = candidate.local_audio(pcm, system_pcm, whole_lane=True)
    cleanup_neighbours = tuple(kept)
    restored = []
    holes = cleanup if raw_cleanup is None else raw_cleanup
    for run, samples in rule.uncovered_runs(holes, witness, skip=skip):
        if samples < rule.MIN_RUN_SAMPLES:
            continue
        voiced = tuple(gate.webrtc_gate.filter(pcm, run))
        local, stretches, rows = candidate.local_words(flags, voiced, 0)
        # An anchored lane never substitutes for this independent local-run requirement.
        admitted = candidate._evidenced(voiced, local)
        if admitted:
            gated = candidate.filter_terminal(gate, pcm, admitted, system_words, system_pcm16=system_pcm)
            admitted = candidate._evidenced(gated, local)
        label = None
        if admitted:
            a = admitted[0].start_sample
            b = max(rule._span(w)[1] for w in admitted)
            neighbours = [w for w in cleanup_neighbours if w.end_sample <= a or w.start_sample >= b]
            if neighbours:
                near = min(neighbours, key=lambda w: (max(a - w.end_sample, w.start_sample - b, 0), w.start_sample))
                label = near.speaker
            else:
                label = 'local'
            kept.extend(GeminiWord(w.text, label, w.start_sample, rule._span(w)[1]) for w in admitted)
            restored.append({'text': [w.text for w in admitted], 'start_s': a / S, 'end_s': b / S,
                             'uncovered_s': samples / S, 'speaker': label})
        LOG.append({'candidate': candidate._words(run), 'voiced': candidate._words(voiced),
                    'local_words': len(local), 'local_speech_seen': gate.local_speech_seen,
                    'stretches': candidate._spans(stretches), 'runs': rows,
                    'admitted': candidate._words(admitted), 'assigned_label': label})
    return tuple(sorted(kept, key=lambda w: (w.start_sample, w.end_sample))), restored


def w_labels(words, pcm, encoder, *, enabled, chunks=None):
    """Execute the frozen W Engine on system words BEFORE H; text/times unchanged."""
    if not enabled:
        return tuple(words), None
    with tempfile.TemporaryDirectory(prefix='r5bc-w-') as tmp:
        path = Path(tmp) / 'public-system.wav'
        sf.write(path, np.frombuffer(pcm, dtype='<i2'), S, subtype='PCM_16')
        source = chunks or [type('Chunk', (), {'index': 0, 'start_sample': 0, 'end_sample': len(pcm)//2,
                                             'core_end_sample': len(pcm)//2, 'words': words})()]
        records = []
        i = 0
        for chunk in source:
            rows = []
            for word in chunk.words:
                rows.append({'i': i, 'text': word.text, 'label': word.speaker,
                             'start_s': word.start_sample/S, 'end_s': word.end_sample/S})
                i += 1
            records.append({'index': chunk.index, 'start_s': chunk.start_sample/S,
                            'end_s': chunk.end_sample/S, 'core_end_s': chunk.core_end_sample/S, 'words': rows})
        engine = w_rule.Engine({'case_id': 'bc-system', 'audio_path': str(path), 'chunks': records}, encoder=encoder)
        groups = {r['i']: r['group'] for r in engine.merge(enabled=True)}
        output = []
        for record in records:
            for raw in record['words']:
                if record['start_s'] <= (raw['start_s']+raw['end_s'])/2 < record['core_end_s']:
                    output.append(GeminiWord(raw['text'], groups[raw['i']], round(raw['start_s']*S), round(raw['end_s']*S)))
        return tuple(output), engine.state()
