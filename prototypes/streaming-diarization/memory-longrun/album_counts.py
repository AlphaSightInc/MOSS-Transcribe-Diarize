"""Count-only supplemental replay. Native memory numbers from this run are INVALID.
Question: exact exemplar counts behind the main profile's speaker-bank counters.
Cache only byte-identical WAV + intervals; real pinned ONNX computes each unique input.
This changes computation reuse, not the vectors observed by production identity policy.
Falsifier: count checkpoints differ from uncached owner banks or content changes.
No hash, no persistent cache, no model/policy change. Interpret ONLY object counts.
"""
import sys
from pathlib import Path
import memory_profile as bench
original=bench.bundle._identity_encoder
stats={'calls':0,'unique':0}
def cached(config):
    encoder=original(config); embed=encoder.embed; cache={}
    def run(wav_path,intervals):
        stats['calls']+=1
        key=(Path(wav_path).read_bytes(),tuple(intervals))
        if key not in cache:
            cache[key]=embed(wav_path,intervals);stats['unique']+=1
        return list(cache[key])
    encoder.embed=run
    return encoder
bench.bundle._identity_encoder=cached
# Tracing millions of mixer temporaries is unnecessary in a count-only replay.
class NoTrace:
    @staticmethod
    def start(*args): pass
    @staticmethod
    def get_traced_memory(): return (0,0)
    @staticmethod
    def get_tracemalloc_memory(): return 0
    @staticmethod
    def take_snapshot(): return NoTrace()
    def statistics(self,*args): return []
bench.tracemalloc=NoTrace
bench.main()
print(stats)
