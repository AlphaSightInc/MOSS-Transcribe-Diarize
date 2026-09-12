"""Scratch-process ablation only; never install in a deployment launcher."""
import os,runpy,sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
scratch = Path(os.environ['MOSS_DIFFERENTIAL_SCRATCH'])
sys.path.insert(0, str(scratch))
if os.environ['MOSS_ATTRIBUTION_ARM'] == 'ends_only':
    from dataclasses import replace
    from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixer
    original = LiveCompatibilityMixer._stage
    def stage(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if result is not None:
            result = replace(result, frame=replace(result.frame, analysis_pcm=None))
        return result
    LiveCompatibilityMixer._stage = stage
runpy.run_path(str(scratch/'run_stack.py'), run_name='__main__')
