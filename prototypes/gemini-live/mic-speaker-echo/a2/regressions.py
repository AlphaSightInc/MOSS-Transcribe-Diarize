"""Run recorded-pattern regressions through prototype publication placement, before production."""
import sys,importlib.util,tempfile,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'f1')]
import candidate
rt=candidate.rt
spec=importlib.util.spec_from_file_location('preview_tests',HERE.parents[3]/'tests/gemini/test_gemini_preview_duplication.py')
tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
class ProtoRuntime(rt.GeminiLiveRuntime):
    def __init__(self,**kwargs):
        super().__init__(**kwargs);self.trim=candidate.RememberedTrim()
    def publish_update(self,sid,update):
        if isinstance(update,rt.GeminiPreview):update=rt.GeminiPreview(update.end_sample,self.trim.trim(update.segments,self.snapshot(sid).session.effective_transcript))
        if isinstance(update,rt.GeminiBase) and update.degraded:update=rt.GeminiBase(update.through_sample,self.trim.trim(update.segments,self.snapshot(sid).session.effective_transcript,degraded=True),True)
        super().publish_update(sid,update)
tests.GeminiLiveRuntime=ProtoRuntime
for name in ['test_preview_remembers_proven_cut_after_a_long_solid_omission','test_preview_remembers_proven_cut_after_a_long_preview_insertion','test_proven_preview_cut_does_not_flicker_across_many_frontiers','test_degraded_growing_paragraph_commits_only_its_new_suffix','test_degraded_single_word_is_committed_once_with_witnessed_extent']:
    with tempfile.TemporaryDirectory() as tmp:getattr(tests,name)(Path(tmp))
    print(name,'PASS',flush=True)
